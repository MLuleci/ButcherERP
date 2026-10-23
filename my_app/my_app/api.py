from datetime import date

import frappe
from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict
from erpnext.stock.doctype.batch.batch import Batch
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from erpnext.utilities.transaction_base import get_whole_number_uoms
from frappe import _
from frappe.utils import cint, flt, getdate, sbool, today


def get_bom(bom: str) -> dict:
	"""Get a valid BOM by name."""
	bom_doc = frappe.db.get_value(
		"BOM", bom, 
		[
			"name",
			"uom",
			"item",
			"company",
			"is_active",
			"docstatus",
			"default_source_warehouse",
			"default_target_warehouse",
		], 
		as_dict=True
	)

	if not bom_doc:
		frappe.throw(_("BOM {0} not found").format(bom))
	if not bom_doc.is_active:
		frappe.throw(_("BOM {0} is not active").format(bom))
	if bom_doc.docstatus != 1:
		frappe.throw(_("BOM {0} is not submitted").format(bom))

	return bom_doc


def get_fg(item: str) -> dict:
	"""Get a valid finished-good item by name."""
	fg_doc = frappe.db.get_value(
		"Item", item, 
		[
			"name",
			"item_name",
			"has_batch_no",
			"batch_number_series",
			"shelf_life_in_days",
			"stock_uom",
			"disabled"
		],
		as_dict=True
	)

	if not fg_doc:
		frappe.throw(_("Item {0} not found").format(item))
	if fg_doc.disabled:
		frappe.throw(_("Item {0} is disabled").format(item))
	if not fg_doc.has_batch_no:
		frappe.throw(_("Item {0} does not have batch numbers").format(item))

	return fg_doc


def validate_fg_qty(qty: float, uom: str, whole_number_uoms: set | None = None):
	"""Reject a fractional finished-goods quantity in a whole-number unit."""
	if whole_number_uoms is None:
		whole_number_uoms = get_whole_number_uoms([uom])
	if uom in whole_number_uoms and qty != cint(qty):
		frappe.throw(_("Quantity must be a whole number for unit {0}").format(uom))


def entry_summary(se: StockEntry) -> dict:
	"""Summarise a submitted Manufacture Stock Entry."""
	fg_row = next(row for row in se.items if row.is_finished_item)
	settings = frappe.get_single("My App Settings")
	return {
		"name": se.name,
		"batch_no": fg_row.batch_no,
		"item_code": fg_row.item_code,
		"item_name": fg_row.item_name,
		"qty": flt(fg_row.qty),
		"uom": fg_row.uom,
		"must_be_whole_number": bool(get_whole_number_uoms([fg_row.uom])),
		"production_date": str(se.posting_date),
		"expiry_date": str(frappe.db.get_value("Batch", fg_row.batch_no, "expiry_date")),
		"is_finished": fg_row.t_warehouse == settings.target_warehouse,
	}


def get_tolerance_percent(bom: str) -> float:
	"""Allowed difference between chosen and required item quantities, in percent."""
	return (
		flt(frappe.db.get_value("BOM", bom, "pda_tolerance_percent"))
		or flt(frappe.db.get_single_value("My App Settings", "default_tolerance_percent"))
		or 5.0
	)


@frappe.whitelist()
def get_bom_details(bom, qty, explode=False):
	"""Return BOM items scaled to qty, plus finished-good metadata."""
	qty = flt(qty)
	if not qty:
		frappe.throw(_("Invalid quantity"))

	explode = sbool(explode)

	bom_doc = get_bom(bom)
	fg_doc = get_fg(bom_doc.item)

	bom_items = get_bom_items_as_dict(
		bom,
		bom_doc.company,
		qty=qty,
		fetch_exploded=explode,
		# e.g. spices may be stocked as Nos or Kgs
		# but be used in grams in the BOM
		fetch_qty_in_stock_uom=False
	)

	whole_number_uoms = get_whole_number_uoms(
		[bom_doc.uom] + [item.uom or item.stock_uom for item in bom_items.values()]
	)
	validate_fg_qty(qty, bom_doc.uom, whole_number_uoms)

	# Ingredient details:
	items = []
	for item_code, item in bom_items.items():
		items.append(
			{
				"item_code": item_code,
				"item_name": item.item_name,
				"qty": flt(item.qty, 3),
				"uom": item.uom or item.stock_uom,
				"must_be_whole_number": (item.uom or item.stock_uom) in whole_number_uoms,
				"stock_uom": item.stock_uom,
				"conversion_factor": flt(item.get("conversion_factor")) or 1.0,
			}
		)

	return {
		"name": bom_doc.name,
		"qty": qty,
		"item_code": fg_doc.name,
		"item_name": fg_doc.item_name,
		"uom": bom_doc.uom,
		"must_be_whole_number": bom_doc.uom in whole_number_uoms,
		"stock_uom": fg_doc.stock_uom,
		"shelf_life_in_days": int(fg_doc.shelf_life_in_days or 0),
		"tolerance_percent": get_tolerance_percent(bom),
		"items": items,
	}


@frappe.whitelist()
def create_manufacture_entry(bom, qty, items, expiry_date=None, explode=False, is_finished=True, request_id=None):
	"""Create and submit a Manufacture Stock Entry."""
	if request_id:
		existing = frappe.db.get_value("Stock Entry", {"pda_request_id": request_id, "docstatus": 1}, "name")
		if existing:
			return entry_summary(frappe.get_doc("Stock Entry", existing))

	qty = flt(qty)
	if not qty:
		frappe.throw(_("Invalid quantity"))

	explode = sbool(explode)
	is_finished = sbool(is_finished)

	if not expiry_date:
		frappe.throw(_("Expiry date is required"))
	try:
		expiry_date = date.fromisoformat(str(expiry_date))
	except ValueError:
		frappe.throw(_("Invalid expiry date"))
	if expiry_date <= getdate(today()):
		frappe.throw(_("Expiry date must be after today"))

  # { [item_code]: { [batch_no]: quantity } } 
	items: dict[str, dict[str, float]] = frappe.parse_json(items)
	bom_doc = get_bom(bom)
	validate_fg_qty(qty, bom_doc.uom)
	fg_doc = get_fg(bom_doc.item)

	bom_items = get_bom_items_as_dict(
		bom,
		bom_doc.company,
		qty=qty,
		fetch_exploded=explode,
		fetch_qty_in_stock_uom=False
	)

	# Verify included items match BOM:
	missing = bom_items.keys() - items.keys()
	extra = items.keys() - bom_items.keys()
	if missing or extra:
		frappe.throw(_("Items do not match BOM. Missing: {0}. Not in BOM: {1}").format(
			", ".join(bom_items[i].item_name for i in missing) or "-",
			", ".join(extra) or "-",
		))

	tolerance = get_tolerance_percent(bom)
	whole_number_uoms = get_whole_number_uoms(item.uom or item.stock_uom for item in bom_items.values())
	for item_code, batches in items.items():
		item = bom_items[item_code]
		is_whole = (item.uom or item.stock_uom) in whole_number_uoms
		for batch_no, quantity in batches.items():
			batches[batch_no] = flt(quantity)
			if batches[batch_no] <= 0:
				frappe.throw(_("Quantity for batch {0} must be greater than zero").format(batch_no))
			if is_whole and batches[batch_no] != cint(batches[batch_no]):
				frappe.throw(_("Quantity for batch {0} must be a whole number").format(batch_no))

		required = flt(item.qty)
		chosen = sum(batches.values())
		# Whole-number units can't meet a percentage on small quantities, so allow ±0.5 instead
		allowed = 0.5 if is_whole else required * tolerance / 100
		if abs(chosen - required) > allowed + 0.0005:
			if is_whole:
				frappe.throw(_("{0}: {1} used, {2} required (±0.5)").format(
					item.item_name, flt(chosen, 3), flt(required, 3)))
			frappe.throw(_("{0}: {1} used, {2} required (±{3}%)").format(
				item.item_name, flt(chosen, 3), flt(required, 3), tolerance))

	settings = frappe.get_single("My App Settings")
	if not settings.source_warehouse or not settings.target_warehouse:
		frappe.throw(_("Please configure source and target warehouses in My App Settings."))

	# Stock Entry common details:
	se: StockEntry = frappe.new_doc("Stock Entry")
	se.purpose = "Manufacture"
	se.from_bom = 1
	se.bom_no = bom
	se.company = bom_doc.company
	se.fg_completed_qty = qty
	se.pda_request_id = request_id

	# Add ingredients:
	for item_code, batches in items.items():
		item = bom_items.get(item_code)
		for batch_no, quantity in batches.items():
			batch_item = frappe.db.get_value("Batch", batch_no, "item")
			if not batch_item:
				frappe.throw(_("Batch {0} not found").format(batch_no))
			if batch_item != item_code:
				frappe.throw(_("Batch {0} is for item {1} not {2}").format(batch_no, batch_item, item_code))

			se.append(
				"items",
				{
					"item_code": item_code,
					"qty": quantity,
					"uom": item.uom or item.stock_uom,
					"stock_uom": item.stock_uom,
					"conversion_factor": flt(item.get("conversion_factor")) or 1.0,
					# We always take from the source warehouse for simplicity
					"s_warehouse": settings.source_warehouse,
					"is_finished_item": 0,
					"batch_no": batch_no,
					"use_serial_batch_fields": 1,
				},
			)

	# Finished-goods batch:
	fg_batch: Batch = frappe.new_doc("Batch")
	fg_batch.item = bom_doc.item
	fg_batch.expiry_date = expiry_date
	fg_batch.insert(ignore_permissions=True)

	# Add finished-goods:
	se.append(
		"items",
		{
			"item_code": bom_doc.item,
			"qty": qty,
			# BOM can't use a UOM different from the stock UOM for finished-goods
			"uom": fg_doc.stock_uom,
			"stock_uom": fg_doc.stock_uom,
			"conversion_factor": 1.0,
			# If this finished-good is a sub-assembly itself, send it to the source warehouse
			"t_warehouse": settings.target_warehouse if is_finished else settings.source_warehouse,
			"is_finished_item": 1,
			"batch_no": fg_batch.name,
			"use_serial_batch_fields": 1,
		},
	)

	se.set_stock_entry_type()
	se.insert()
	se.submit()

	return entry_summary(se)

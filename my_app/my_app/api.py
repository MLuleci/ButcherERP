import json
from datetime import date

import frappe
from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict
from erpnext.stock.doctype.batch.batch import Batch
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from frappe import _
from frappe.utils import flt, sbool, today


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
			"default_source_warehouse",
			"default_target_warehouse",
		], 
		as_dict=True
	)

	if not bom_doc:
		frappe.throw(_("BOM {0} not found").format(bom))
	if not bom_doc.is_active:
		frappe.throw(_("BOM {0} is not active").format(bom))

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

	# Ingredient details:
	items = []
	for item_code, item in bom_items.items():
		items.append(
			{
				"item_code": item_code,
				"item_name": item.item_name,
				"qty": flt(item.qty),
				"uom": item.uom or item.stock_uom,
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
		"stock_uom": fg_doc.stock_uom,
		"shelf_life_in_days": int(fg_doc.shelf_life_in_days or 0),
		"items": items,
	}


@frappe.whitelist()
def create_manufacture_entry(bom, qty, items, expiry_date=None, explode=False, is_finished=True):
	"""Create and submit a Manufacture Stock Entry."""
	qty = flt(qty)
	if not qty:
		frappe.throw(_("Invalid quantity"))

	explode = sbool(explode)
	is_finished = sbool(is_finished)

	try:
		expiry_date = date.fromisoformat(expiry_date) if expiry_date else None
	except ValueError:
		frappe.throw(_("Invalid expiry date"))

  # { [item_code]: { [batch_no]: quantity } } 
	items: dict[str, dict[str, float]] = json.loads(items)
	bom_doc = get_bom(bom)
	fg_doc = get_fg(bom_doc.item)

	bom_items = get_bom_items_as_dict(
		bom,
		bom_doc.company,
		qty=qty,
		fetch_exploded=explode,
		fetch_qty_in_stock_uom=False
	)

	# Verify included items match BOM:
	if items.keys() != bom_items.keys():
		frappe.throw(_("Items do not match BOM"))

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

	# Add ingredients:
	for item_code, batches in items.items():
		item = bom_items.get(item_code)
		for batch_no, quantity in batches.items():
			batch_doc = frappe.db.get_value("Batch", batch_no, ["item"], as_dict=True)
			batch_item = batch_doc["item"]
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
	if expiry_date:
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

	return {
		"name": se.name,
		"batch_no": fg_batch.name,
		"item_name": fg_doc.name,
		"production_date": today(),
		"expiry_date": str(expiry_date) if expiry_date else None,
		"is_finished": is_finished
	}

import json

import frappe
from frappe import _
from frappe.utils import flt, today


@frappe.whitelist()
def get_bom_details(bom, qty):
	"""Return BOM items scaled to qty, plus finished-good metadata."""
	qty = flt(qty) or 1.0

	bom_doc = frappe.db.get_value(
		"BOM", bom, ["item", "item_name", "company", "is_active"], as_dict=1
	)
	if not bom_doc:
		frappe.throw(_("BOM {0} not found").format(bom))
	if not bom_doc.is_active:
		frappe.throw(_("BOM {0} is not active").format(bom))

	fg_item = frappe.db.get_value(
		"Item", bom_doc.item, ["has_serial_no", "serial_no_series", "item_name", "shelf_life_in_days"], as_dict=1
	)

	default_source = frappe.db.get_single_value("My App Settings", "source_warehouse")

	from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict

	item_dict = get_bom_items_as_dict(
		bom,
		bom_doc.company,
		qty=qty,
		fetch_exploded=1,
		fetch_qty_in_stock_uom=False,
	)

	company = bom_doc.company
	items = []
	for item_code, d in item_dict.items():
		item_default_warehouse = frappe.db.get_value(
			"Item Default",
			{"parent": item_code, "company": company},
			"default_warehouse",
		)
		items.append(
			{
				"item_code": item_code,
				"item_name": d.item_name,
				"qty": flt(d.qty),
				"uom": d.uom or d.stock_uom,
				"stock_uom": d.stock_uom,
				"conversion_factor": flt(d.get("conversion_factor")) or 1.0,
				"s_warehouse": d.source_warehouse or item_default_warehouse or default_source,
			}
		)

	return {
		"fg_item": bom_doc.item,
		"fg_item_name": fg_item.item_name if fg_item else bom_doc.item,
		"has_serial_no": int(fg_item.has_serial_no) if fg_item else 0,
		"serial_no_series": fg_item.serial_no_series if fg_item else "",
		"shelf_life_in_days": int(fg_item.shelf_life_in_days or 0) if fg_item else 0,
		"company": bom_doc.company,
		"items": items,
	}


@frappe.whitelist()
def create_manufacture_entry(bom, fg_qty, items, expiry_date=None):
	"""Create and submit a Manufacture Stock Entry."""
	fg_qty = flt(fg_qty)
	if isinstance(items, str):
		items = json.loads(items)
	expiry_date = expiry_date or None

	settings = frappe.get_single("My App Settings")
	if not settings.source_warehouse or not settings.target_warehouse:
		frappe.throw(_("Please configure source and target warehouses in My App Settings."))

	bom_meta = frappe.db.get_value("BOM", bom, ["item", "company"], as_dict=1)
	if not bom_meta:
		frappe.throw(_("BOM {0} not found").format(bom))

	fg_item_meta = frappe.db.get_value(
		"Item", bom_meta.item, ["has_serial_no", "serial_no_series"], as_dict=1
	)

	serial_no = ""
	if fg_item_meta and fg_item_meta.has_serial_no and fg_item_meta.serial_no_series:
		serial_no = frappe.model.naming.make_autoname(fg_item_meta.serial_no_series)

	fg_batch_no = ""
	if expiry_date:
		batch = frappe.new_doc("Batch")
		batch.item = bom_meta.item
		batch.expiry_date = expiry_date
		batch.insert(ignore_permissions=True)
		fg_batch_no = batch.name

	se = frappe.new_doc("Stock Entry")
	se.purpose = "Manufacture"
	se.bom_no = bom
	se.company = bom_meta.company
	se.fg_completed_qty = fg_qty
	se.from_warehouse = settings.source_warehouse
	se.to_warehouse = settings.target_warehouse

	for i in items:
		se.append(
			"items",
			{
				"item_code": i["item_code"],
				"qty": flt(i["qty"]),
				"uom": i.get("uom") or "Nos",
				"stock_uom": i.get("stock_uom") or i.get("uom") or "Nos",
				"conversion_factor": flt(i.get("conversion_factor")) or 1.0,
				"s_warehouse": i.get("s_warehouse") or settings.source_warehouse,
				"batch_no": i.get("batch_no") or "",
				"use_serial_batch_fields": 1,
			},
		)

	fg_stock_uom = frappe.db.get_value("Item", bom_meta.item, "stock_uom") or "Nos"
	fg_item_warehouse = frappe.db.get_value(
		"Item Default",
		{"parent": bom_meta.item, "company": bom_meta.company},
		"default_warehouse",
	)
	fg_warehouse = fg_item_warehouse or settings.target_warehouse
	se.append(
		"items",
		{
			"item_code": bom_meta.item,
			"qty": fg_qty,
			"uom": fg_stock_uom,
			"stock_uom": fg_stock_uom,
			"conversion_factor": 1.0,
			"t_warehouse": fg_warehouse,
			"is_finished_item": 1,
			"serial_no": serial_no,
			"batch_no": fg_batch_no,
			"use_serial_batch_fields": 1,
		},
	)

	se.use_serial_batch_fields = 1
	se.set_stock_entry_type()
	se.insert()
	se.submit()

	return {
		"stock_entry": se.name,
		"serial_no": serial_no,
		"batch_no": fg_batch_no,
		"fg_item_name": frappe.db.get_value("Item", bom_meta.item, "item_name"),
		"production_date": today(),
		"expiry_date": expiry_date or "",
	}

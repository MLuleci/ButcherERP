import frappe
from frappe.permissions import add_permission, update_permission_property

# Everything the PDA app reads or creates, so PDA users don't need Stock User or Manufacturing User
PDA_PERMISSIONS = {
	"Batch": ["read", "select"],
	"BOM": ["read", "select"],
	"Item": ["read", "select"],
	# Frappe's submit() saves the document, which needs write
	"Stock Entry": ["read", "select", "create", "write", "submit"],
	# ERPNext creates and submits one for each batch row when the Stock Entry is submitted
	"Serial and Batch Bundle": ["read", "select", "create", "write", "submit"],
	"UOM": ["read", "select"],
	"Warehouse": ["read", "select"],
}


def after_migrate():
	setup_pda_permissions()
	enable_language("bg")


def setup_pda_permissions():
	for doctype, ptypes in PDA_PERMISSIONS.items():
		filters = {"parent": doctype, "role": "PDA User", "permlevel": 0}
		if not frappe.db.exists("Custom DocPerm", filters):
			add_permission(doctype, "PDA User")
		current = frappe.db.get_value("Custom DocPerm", filters, ptypes, as_dict=True)
		for ptype in ptypes:
			if not current[ptype]:
				update_permission_property(doctype, "PDA User", 0, ptype, 1)


def stock_entry_has_permission(doc, ptype=None, user=None, debug=False):
	"""PDA User's create and write on Stock Entry are only for manufacturing from a BOM."""
	roles = frappe.get_roles(user)
	if ptype == "read" or "PDA User" not in roles:
		return True
	# Other roles may already allow more, e.g. Stock User
	if set(roles) - {"PDA User", "All", "Guest", "Desk User"}:
		return True
	return doc.purpose == "Manufacture" and bool(doc.from_bom)


def enable_language(lang):
	"""Accept-Language is ignored for disabled languages."""
	language = frappe.get_doc("Language", lang)
	if not language.enabled:
		language.enabled = 1
		language.save()

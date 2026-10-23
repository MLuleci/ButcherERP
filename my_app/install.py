import frappe
from frappe.permissions import add_permission, update_permission_property


def after_migrate():
	setup_pda_permissions()
	enable_language("bg")


def setup_pda_permissions():
	"""Let PDA users read Batches. Stock and Manufacturing users can only select them."""
	if frappe.db.exists("Custom DocPerm", {"parent": "Batch", "role": "PDA User", "permlevel": 0}):
		return
	add_permission("Batch", "PDA User")
	update_permission_property("Batch", "PDA User", 0, "select", 1)


def enable_language(lang):
	"""Accept-Language is ignored for disabled languages."""
	language = frappe.get_doc("Language", lang)
	if not language.enabled:
		language.enabled = 1
		language.save()

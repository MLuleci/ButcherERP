frappe.pages["manufacturing-scan"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Manufacturing Scan"),
		single_column: true,
	});

	new ManufacturingScanPage(page);
};

class ManufacturingScanPage {
	constructor(page) {
		this.page = page;
		this.bom_data = null;
		this.render_step1();
	}

	// ─── Step 1: BOM + Qty selection ────────────────────────────────────────────

	render_step1() {
		this.page.main.html(`
			<div class="mfg-scan-container" style="max-width:600px;margin:24px auto;padding:0 16px;">
				<div class="frappe-card" style="padding:24px;">
					<h5 style="margin-bottom:20px;">${__("Select BOM and Quantity")}</h5>

					<div class="form-group">
						<label class="control-label">${__("Bill of Materials")}</label>
						<div id="bom-field-wrap"></div>
					</div>

					<div class="form-group" style="margin-top:16px;">
						<label class="control-label">${__("Finished Goods Quantity")}</label>
						<input id="fg-qty" type="number" min="0.001" step="any" value="1"
							class="form-control" style="max-width:200px;">
					</div>

					<button id="btn-load" class="btn btn-primary" style="margin-top:20px;">
						${__("Load Materials")}
					</button>
				</div>
			</div>
		`);

		// Frappe Link control for BOM
		this.bom_control = frappe.ui.form.make_control({
			parent: this.page.main.find("#bom-field-wrap")[0],
			df: {
				fieldtype: "Link",
				fieldname: "bom_no",
				options: "BOM",
				placeholder: __("Search BOM…"),
				filters: { is_active: 1, docstatus: 1 },
			},
			render_input: true,
		});
		this.bom_control.refresh();

		this.page.main.find("#btn-load").on("click", () => this.load_bom());
	}

	load_bom() {
		const bom = this.bom_control.get_value();
		const qty = parseFloat(this.page.main.find("#fg-qty").val());

		if (!bom) {
			frappe.msgprint({ title: __("Required"), message: __("Please select a BOM."), indicator: "orange" });
			return;
		}
		if (!qty || qty <= 0) {
			frappe.msgprint({ title: __("Required"), message: __("Please enter a valid quantity."), indicator: "orange" });
			return;
		}

		frappe.call({
			method: "my_app.my_app.api.get_bom_details",
			args: { bom, qty },
			freeze: true,
			freeze_message: __("Loading BOM…"),
			callback: (r) => {
				if (r.exc) return;
				this.bom_data = r.message;
				this.bom_data.bom = bom;
				this.bom_data.fg_qty = qty;
				this.render_step2();
			},
		});
	}

	// ─── Step 2: Scan raw-material batches ──────────────────────────────────────

	render_step2() {
		const d = this.bom_data;
		const rows_html = d.items
			.map(
				(item, idx) => `
			<div class="bom-item-row" data-idx="${idx}"
				data-item="${frappe.utils.escape_html(item.item_code)}"
				data-qty="${item.qty}"
				data-uom="${frappe.utils.escape_html(item.uom)}"
				data-warehouse="${frappe.utils.escape_html(item.s_warehouse || "")}"
				style="display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--border-color);">
				<div style="flex:1;min-width:0;">
					<div style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
						${frappe.utils.escape_html(item.item_name)}
					</div>
					<div style="font-size:12px;color:var(--text-muted);">
						${frappe.utils.escape_html(item.item_code)}
					</div>
					<div style="font-size:12px;color:var(--text-muted);">
						${__("Required")}: ${item.qty} ${frappe.utils.escape_html(item.uom)}
					</div>
				</div>
				<div style="min-width:90px;text-align:right;">
					<div class="batch-label" style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">—</div>
					<button class="btn btn-default btn-xs btn-scan-batch" data-idx="${idx}">
						<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
							fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
							stroke-linejoin="round" style="vertical-align:middle;margin-right:3px;">
							<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/>
							<path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/>
							<rect x="7" y="7" width="3" height="9"/><rect x="14" y="7" width="3" height="9"/>
						</svg>
						${__("Scan")}
					</button>
				</div>
			</div>
		`
			)
			.join("");

		this.page.main.html(`
			<div class="mfg-scan-container" style="max-width:600px;margin:24px auto;padding:0 16px;">
				<div class="frappe-card" style="padding:24px;">
					<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
						<h5 style="margin:0;">${__("Scan Batches")}</h5>
						<button id="btn-back" class="btn btn-default btn-xs">${__("← Back")}</button>
					</div>
					<div style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
						${frappe.utils.escape_html(d.fg_item_name)} &mdash; ${d.fg_qty} ${__("units")}
					</div>

					<div class="form-group" style="margin-bottom:16px;">
						<label class="control-label">${__("Days Until Expiry")}</label>
						<input id="fg-expiry-days" type="number" min="0" step="1" class="form-control"
							style="max-width:200px;" value="${d.shelf_life_in_days || ""}">
					</div>

					<div id="bom-rows">${rows_html}</div>

					<button id="btn-submit" class="btn btn-primary" style="margin-top:20px;width:100%;" disabled>
						${__("Submit Stock Entry")}
					</button>
				</div>
			</div>
		`);

		this.page.main.find("#btn-back").on("click", () => this.render_step1());
		this.page.main.find(".btn-scan-batch").on("click", (e) => {
			const idx = parseInt($(e.currentTarget).data("idx"));
			this.open_scanner(idx);
		});
		this.page.main.find("#btn-submit").on("click", () => this.submit_entry());
	}

	check_all_scanned() {
		const rows = this.page.main.find(".bom-item-row");
		const all_done = rows.toArray().every((el) => $(el).data("batch"));
		this.page.main.find("#btn-submit").prop("disabled", !all_done);
	}

	// ─── Camera scanner ─────────────────────────────────────────────────────────

	open_scanner(row_idx) {
		const row = this.page.main.find(`.bom-item-row[data-idx="${row_idx}"]`);
		const item_name = row.find(".batch-label").closest(".bom-item-row").find("div > div:first-child").text().trim();

		// Build modal
		const modal_id = "scan-modal-" + row_idx;
		$(`#${modal_id}`).remove();
		$("body").append(`
			<div id="${modal_id}" style="
				position:fixed;inset:0;z-index:9999;
				background:rgba(0,0,0,0.85);
				display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;">
				<div style="color:#fff;font-size:15px;font-weight:500;padding:0 16px;text-align:center;">
					${__("Scan batch for")} <em>${frappe.utils.escape_html(item_name)}</em>
				</div>
				<div style="position:relative;width:min(90vw,400px);">
					<video id="scan-video-${row_idx}" autoplay playsinline muted
						style="width:100%;border-radius:8px;display:block;"></video>
					<canvas id="scan-canvas-${row_idx}" style="display:none;"></canvas>
					<div style="
						position:absolute;inset:0;border:2px solid rgba(255,255,255,0.5);
						border-radius:8px;pointer-events:none;">
						<div style="
							position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
							width:60%;height:60%;border:2px solid #4CAF50;border-radius:4px;">
						</div>
					</div>
				</div>
				<div style="display:flex;gap:12px;">
					<button id="btn-cancel-scan-${row_idx}" class="btn btn-default">
						${__("Cancel")}
					</button>
					<button id="btn-manual-${row_idx}" class="btn btn-default">
						${__("Enter manually")}
					</button>
				</div>
			</div>
		`);

		const video = document.getElementById(`scan-video-${row_idx}`);
		const canvas = document.getElementById(`scan-canvas-${row_idx}`);
		let stream = null;
		let cancelled = false;

		const close_modal = () => {
			cancelled = true;
			if (stream) stream.getTracks().forEach((t) => t.stop());
			$(`#${modal_id}`).remove();
		};

		const on_result = (batch_id) => {
			close_modal();
			row.data("batch", batch_id);
			row.find(".batch-label").text(batch_id).css("color", "var(--text-color)");
			row.find(".btn-scan-batch").text(__("Re-scan")).addClass("btn-success").removeClass("btn-default");
			this.check_all_scanned();
		};

		$(`#btn-cancel-scan-${row_idx}`).on("click", close_modal);

		$(`#btn-manual-${row_idx}`).on("click", () => {
			close_modal();
			const val = prompt(__("Enter Batch ID:"));
			if (val && val.trim()) on_result(val.trim());
		});

		// Start camera
		navigator.mediaDevices
			.getUserMedia({ video: { facingMode: "environment" } })
			.then((s) => {
				if (cancelled) {
					s.getTracks().forEach((t) => t.stop());
					return;
				}
				stream = s;
				video.srcObject = s;
				video.addEventListener("loadedmetadata", () => {
					canvas.width = video.videoWidth;
					canvas.height = video.videoHeight;
					const is_cancelled = () => cancelled;
					if ("BarcodeDetector" in window) {
						this._scan_with_detector(video, on_result, is_cancelled);
					} else {
						this._scan_with_jsqr(video, canvas, on_result, is_cancelled);
					}
				});
			})
			.catch((err) => {
				close_modal();
				if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
					frappe.msgprint({
						title: __("Camera Permission Denied"),
						message: __("Please allow camera access and try again, or use 'Enter manually'."),
						indicator: "orange",
					});
				} else {
					frappe.msgprint({ title: __("Camera Error"), message: err.message, indicator: "red" });
				}
			});
	}

	async _scan_with_detector(video, on_result, is_cancelled) {
		let formats = ["qr_code", "code_128", "code_39", "ean_13", "ean_8", "upc_a", "upc_e"];
		try {
			const supported = await BarcodeDetector.getSupportedFormats();
			formats = formats.filter((f) => supported.includes(f));
		} catch (_) {}

		const detector = new BarcodeDetector({ formats });

		const scan = async () => {
			if (is_cancelled()) return;
			try {
				const codes = await detector.detect(video);
				if (codes.length) {
					on_result(codes[0].rawValue);
					return;
				}
			} catch (_) {}
			if (!is_cancelled()) requestAnimationFrame(scan);
		};

		requestAnimationFrame(scan);
	}

	_scan_with_jsqr(video, canvas, on_result, is_cancelled) {
		const ctx = canvas.getContext("2d");

		const do_scan = () => {
			if (is_cancelled()) return;
			ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
			const image_data = ctx.getImageData(0, 0, canvas.width, canvas.height);
			if (typeof jsQR !== "undefined") {
				const code = jsQR(image_data.data, canvas.width, canvas.height);
				if (code && code.data) {
					on_result(code.data);
					return;
				}
			}
			if (!is_cancelled()) requestAnimationFrame(do_scan);
		};

		// Lazy-load jsQR only when BarcodeDetector is absent
		if (typeof jsQR === "undefined") {
			frappe.require("/assets/my_app/js/jsqr.min.js", () => {
				if (!is_cancelled()) requestAnimationFrame(do_scan);
			});
		} else {
			requestAnimationFrame(do_scan);
		}
	}

	// ─── Step 3: Label preview ──────────────────────────────────────────────────

	render_step3(result) {
		const { stock_entry, batch_no } = result;
		const se_url = `/app/stock-entry/${stock_entry}`;
		const preview_url = `/printview?doctype=Batch&name=${encodeURIComponent(batch_no)}&format=Batch+Label&no_letterhead=1`;

		this.page.main.html(`
			<div class="mfg-scan-container" style="max-width:600px;margin:24px auto;padding:0 16px;">
				<div class="frappe-card" style="padding:24px;">
					<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
						<h5 style="margin:0;">${__("Batch Label")}</h5>
						<a href="${se_url}" target="_blank" class="btn btn-default btn-xs">
							${__("View Stock Entry")}
						</a>
					</div>

					<iframe id="label-preview" src="${preview_url}"
						style="width:100%;height:220px;border:1px solid var(--border-color);border-radius:4px;">
					</iframe>

					<div style="display:flex;gap:12px;margin-top:20px;">
						<button id="btn-print-label" class="btn btn-primary">${__("Print Label")}</button>
						<button id="btn-new-entry" class="btn btn-default">${__("New Entry")}</button>
					</div>
				</div>
			</div>
		`);

		this.page.main.find("#btn-print-label").on("click", () => this.print_label(batch_no));
		this.page.main.find("#btn-new-entry").on("click", () => {
			this.bom_data = null;
			this.render_step1();
		});
	}

	print_label(batch_no) {
		const url = `/printview?doctype=Batch&name=${encodeURIComponent(batch_no)}&format=Batch+Label&no_letterhead=1`;
		const iframe = document.createElement("iframe");
		iframe.style.cssText = "position:fixed;top:0;left:0;width:0;height:0;border:none;visibility:hidden;";
		iframe.src = url;
		document.body.appendChild(iframe);
		iframe.addEventListener("load", () => {
			setTimeout(() => {
				iframe.contentWindow.print();
				iframe.contentWindow.addEventListener("afterprint", () => iframe.remove());
			}, 400);
		});
	}

	// ─── Submit ─────────────────────────────────────────────────────────────────

	submit_entry() {
		const d = this.bom_data;
		const items = this.page.main
			.find(".bom-item-row")
			.toArray()
			.map((el) => {
				const $el = $(el);
				return {
					item_code: $el.data("item"),
					qty: parseFloat($el.data("qty")),
					uom: $el.data("uom"),
					s_warehouse: $el.data("warehouse"),
					batch_no: $el.data("batch") || "",
				};
			});

		const expiry_days = parseInt(this.page.main.find("#fg-expiry-days").val());
		let expiry_date = "";
		if (expiry_days > 0) {
			const d_exp = new Date();
			d_exp.setDate(d_exp.getDate() + expiry_days);
			expiry_date = d_exp.toISOString().slice(0, 10);
		}

		frappe.call({
			method: "my_app.my_app.api.create_manufacture_entry",
			args: {
				bom: d.bom,
				fg_qty: d.fg_qty,
				items: JSON.stringify(items),
				expiry_date,
			},
			freeze: true,
			freeze_message: __("Creating Stock Entry…"),
			callback: (r) => {
				if (r.exc) {
					frappe.msgprint({ title: __("Submission Failed"), message: r.exc, indicator: "red" });
					return;
				}
				this.render_step3(r.message);
			},
		});
	}
}

// Phase 10.2.2: Sales Invoice - Upload Pedimento Button
// Adds "Upload Pedimento" button to Sales Invoice form

frappe.ui.form.on('Sales Invoice', {
    refresh: function(frm) {
        // Only show for saved documents
        if (frm.is_new()) return;
        
        // Add Upload Pedimento button
        frm.add_custom_button(__('Upload Pedimento'), function() {
            upload_pedimento(frm);
        }, __('Documents'));
    }
});

function upload_pedimento(frm) {
    // Open file picker dialog
    frappe.prompt({
        fieldtype: 'Attach',
        fieldname: 'pedimento_file',
        label: __('Select Pedimento (PDF)'),
        description: __('Only PDF files are allowed'),
        reqd: 1
    }, function(values) {
        if (!values.pedimento_file) {
            frappe.msgprint(__('Please select a PDF file'));
            return;
        }
        
        // Check if it's a PDF
        if (!values.pedimento_file.endsWith('.pdf')) {
            frappe.msgprint(__('Only PDF files are allowed'));
            return;
        }
        
        // Upload the file
        frm.call({
            method: 'raven_ai_agent.api.sales_invoice_upload.upload_pedimento',
            args: {
                sales_invoice_name: frm.doc.name,
                file_url: values.pedimento_file
            },
            freeze: true,
            freeze_message: __('Uploading Pedimento to Drive...'),
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.msgprint({
                        title: __('Success'),
                        message: r.message.message,
                        indicator: 'green'
                    });
                    
                    // Refresh the form to show the linked file
                    frm.refresh();
                    
                    // Show link to Drive file
                    if (r.message.drive_file) {
                        frappe.show_alert({
                            message: __('Pedimento saved to Drive'),
                            indicator: 'green'
                        });
                    }
                }
            },
            error: function(r) {
                frappe.msgprint({
                    title: __('Error'),
                    message: r.message || __('Failed to upload Pedimento'),
                    indicator: 'red'
                });
            }
        });
    }, __('Upload Pedimento'), __('Upload'));
}

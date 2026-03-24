// Phase 10.4: Unified Documents Panel
// Groups customer_po_file, pedimento_file, and other document fields into one panel

frappe.ui.form.on('Sales Order', {
    refresh: function(frm) {
        console.log("Documents panel JS loaded for Sales Order:", frm.doc.name);
        add_documents_panel(frm, 'Sales Order');
    }
});

frappe.ui.form.on('Sales Invoice', {
    refresh: function(frm) {
        console.log("Documents panel JS loaded for Sales Invoice:", frm.doc.name);
        add_documents_panel(frm, 'Sales Invoice');
    }
});

function add_documents_panel(frm, doctype) {
    // Only show for saved documents
    if (frm.is_new()) return;
    
    console.log("Adding documents panel for", doctype, frm.doc.name);
    
    // Define document fields for each doctype
    var docFields = [];
    
    if (doctype === 'Sales Order') {
        docFields = [
            {
                fieldname: 'customer_po_file',
                label: 'Customer PO',
                role: 'Customer PO',
                api_method: 'raven_ai_agent.api.sales_order_upload.upload_customer_po'
            }
        ];
    } else if (doctype === 'Sales Invoice') {
        docFields = [
            {
                fieldname: 'pedimento_file',
                label: 'Pedimento',
                role: 'Pedimento',
                api_method: 'raven_ai_agent.api.sales_invoice_upload.upload_pedimento'
            }
        ];
    }
    
    // Create the documents section
    var html = '<div class="documents-panel" style="margin-top: 15px;">';
    html += '<h4 style="margin-bottom: 10px;">📁 Documents</h4>';
    html += '<div class="row">';
    
    docFields.forEach(function(docField) {
        var currentValue = frm.doc[docField.fieldname];
        var status = currentValue ? 'uploaded' : 'not_uploaded';
        var statusText = currentValue ? 'Uploaded' : 'Not uploaded';
        var statusClass = currentValue ? 'text-success' : 'text-muted';
        
        html += '<div class="col-md-6" style="margin-bottom: 10px;">';
        html += '<div class="card" style="padding: 10px;">';
        html += '<div class="row align-items-center">';
        html += '<div class="col-md-8">';
        html += '<label style="font-weight: bold; margin-bottom: 5px;">' + docField.label + '</label>';
        html += '<div class="' + statusClass + '" style="font-size: 12px;">';
        
        if (currentValue) {
            html += '<i class="fa fa-check-circle"></i> ' + statusText;
            html += '<br><small>' + currentValue + '</small>';
        } else {
            html += '<i class="fa fa-times-circle"></i> ' + statusText;
        }
        
        html += '</div></div>';
        html += '<div class="col-md-4 text-right">';
        
        if (currentValue) {
            // View button
            html += '<button class="btn btn-sm btn-default" onclick="view_drive_file(\'' + currentValue + '\')">';
            html += '<i class="fa fa-eye"></i> View</button> ';
        }
        
        // Upload/Replace button
        var btnLabel = currentValue ? 'Replace' : 'Upload';
        html += '<button class="btn btn-sm btn-primary" onclick="upload_document_field(frm, \'' + docField.fieldname + '\', \'' + docField.role + '\', \'' + docField.api_method + '\')">';
        html += '<i class="fa fa-upload"></i> ' + btnLabel + '</button>';
        
        html += '</div></div></div></div>';
    });
    
    html += '</div></div>';
    
    // Add to the form (after the main content)
    frm.add_custom_html(__('Documents'), html, .5);
}

// Global functions for button handlers
function upload_document_field(frm, fieldname, file_role, api_method) {
    // Open file picker dialog
    frappe.prompt({
        fieldtype: 'Attach',
        fieldname: 'document_file',
        label: __('Select Document (PDF)'),
        description: __('Only PDF files are allowed'),
        reqd: 1
    }, function(values) {
        if (!values.document_file) {
            frappe.msgprint(__('Please select a PDF file'));
            return;
        }
        
        // Check if it's a PDF
        if (!values.document_file.endsWith('.pdf')) {
            frappe.msgprint(__('Only PDF files are allowed'));
            return;
        }
        
        // Determine the args based on doctype
        var args = {};
        if (frm.doctype === 'Sales Order') {
            args.sales_order_name = frm.doc.name;
        } else if (frm.doctype === 'Sales Invoice') {
            args.sales_invoice_name = frm.doc.name;
        }
        args.file_url = values.document_file;
        
        // Upload the file
        frm.call({
            method: api_method,
            args: args,
            freeze: true,
            freeze_message: __('Uploading document to Drive...'),
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.msgprint({
                        title: __('Success'),
                        message: r.message.message,
                        indicator: 'green'
                    });
                    
                    // Refresh the form
                    frm.refresh();
                    
                    frappe.show_alert({
                        message: __('Document saved to Drive'),
                        indicator: 'green'
                    });
                }
            },
            error: function(r) {
                frappe.msgprint({
                    title: __('Error'),
                    message: r.message || __('Failed to upload document'),
                    indicator: 'red'
                });
            }
        });
    }, __('Upload Document'), __('Upload'));
}

function view_drive_file(file_name) {
    // Open the Drive file in a new tab or dialog
    frappe.db.get_value('Drive File', file_name, 'file').then(function(r) {
        if (r && r.message && r.message.file) {
            window.open(r.message.file, '_blank');
        } else {
            frappe.msgprint(__('File not found'));
        }
    });
}

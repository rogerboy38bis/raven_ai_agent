# -*- coding: utf-8 -*-
"""
Phase 10.3: Bulk Import Command
Bench command: bench drive-import

Usage:
    bench drive-import --csv /path/to/mapping.csv
    bench drive-import --csv /path/to/mapping.csv --dry-run
    bench drive-import --directory /path/to/files --doctype "Sales Order" --role "Customer PO"
"""

import click
import frappe
from frappe.commands import pass_context
from frappe.utils import now_datetime


@click.command("drive-import")
@click.option("--csv", "csv_path", type=click.Path(exists=True), help="Path to CSV mapping file")
@click.option("--directory", "directory", type=click.Path(exists=True), help="Path to directory with files")
@click.option("--doctype", "doctype", type=str, help="Target DocType (for directory import)")
@click.option("--role", "file_role", type=str, help="File role (e.g., Customer PO, Pedimento)")
@click.option("--dry-run", is_flag=True, help="Validate without uploading")
@click.option("--skip-existing", is_flag=True, default=True, help="Skip if file already exists")
@click.option("--batch-size", type=int, default=50, help="Batch size for CSV import")
@click.option("--pattern", "filename_pattern", type=str, help="Filename pattern to parse docname")
@pass_context
def drive_import(context, csv_path, directory, doctype, file_role, dry_run, skip_existing, batch_size, filename_pattern):
    """
    Bulk import files to Drive and link to DocTypes.
    
    Examples:
        bench drive-import --csv /home/frappe/mapping.csv
        bench drive-import --csv /home/frappe/mapping.csv --dry-run
        bench drive-import --directory /home/frappe/pdfs --doctype "Sales Order" --role "Customer PO"
    """
    frappe.init(site=context.sites[0] if context.sites else None)
    frappe.connect()
    
    try:
        from raven_ai_agent.api.drive_file_helper import (
            bulk_import_from_csv,
            bulk_import_from_directory
        )
        
        if csv_path:
            click.echo(f"Starting bulk import from CSV: {csv_path}")
            click.echo(f"Dry run: {dry_run}")
            click.echo(f"Skip existing: {skip_existing}")
            click.echo(f"Batch size: {batch_size}")
            
            results = bulk_import_from_csv(
                csv_path=csv_path,
                dry_run=dry_run,
                skip_existing=skip_existing,
                batch_size=batch_size
            )
            
        elif directory:
            if not doctype or not file_role:
                click.echo("Error: --doctype and --role are required for directory import", err=True)
                return
            
            click.echo(f"Starting bulk import from directory: {directory}")
            click.echo(f"Target: {doctype} - {file_role}")
            click.echo(f"Dry run: {dry_run}")
            
            results = bulk_import_from_directory(
                directory=directory,
                target_doctype=doctype,
                file_role=file_role,
                filename_pattern=filename_pattern,
                dry_run=dry_run,
                skip_existing=skip_existing
            )
            
        else:
            click.echo("Error: Either --csv or --directory must be specified", err=True)
            return
        
        # Print results
        click.echo("\n" + "="*50)
        click.echo("IMPORT RESULTS")
        click.echo("="*50)
        click.echo(f"Total files: {results['total']}")
        click.echo(f"Successful: {results['success']}")
        click.echo(f"Skipped: {results['skipped']}")
        click.echo(f"Failed: {results['failed']}")
        
        if results.get("dry_run"):
            click.echo("\n(Dry run - no files were actually uploaded)")
        
        if results["errors"]:
            click.echo("\nERRORS:")
            for error in results["errors"][:10]:  # Show first 10 errors
                click.echo(f"  - {error.get('file')}: {error.get('error')}")
            
            if len(results["errors"]) > 10:
                click.echo(f"  ... and {len(results['errors']) - 10} more errors")
        
        if results["success"] > 0 and not dry_run:
            click.echo(f"\n{results['success']} files imported successfully!")
        
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise
        
    finally:
        frappe.destroy()


@click.command("drive-status")
@click.option("--doctype", "doctype", type=str, required=True, help="DocType to check")
@click.option("--role", "file_role", type=str, required=True, help="File role to check")
@pass_context
def drive_status(context, doctype, file_role):
    """
    Show documents without a specific file type.
    
    Example:
        bench drive-status --doctype "Sales Order" --role "Customer PO"
    """
    frappe.init(site=context.sites[0] if context.sites else None)
    frappe.connect()
    
    try:
        from raven_ai_agent.api.drive_file_helper import get_documents_without_file
        
        click.echo(f"Checking {doctype} documents without {file_role}...")
        
        docs = get_documents_without_file(doctype, file_role)
        
        click.echo(f"\nFound {len(docs)} documents without {file_role}:")
        
        for doc in docs[:20]:  # Show first 20
            click.echo(f"  - {doc.get('name')} (Customer: {doc.get('customer', 'N/A')})")
        
        if len(docs) > 20:
            click.echo(f"  ... and {len(docs) - 20} more")
        
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise
        
    finally:
        frappe.destroy()


commands = [drive_import, drive_status]

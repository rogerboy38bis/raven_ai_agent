"""Weight Capture API for AMB Manufacturing Workflow.

Server-side API endpoints for the RPi weight capture system.

Endpoints:
- submit_weight_reading: Submit weight from scale device
- get_device_config: Get device configuration
- validate_barrel_serial: Validate barrel exists in system

Requires Frappe framework and amb_w_tds app.
"""
import frappe
from frappe import _
from frappe.utils import now, now_datetime
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Allowed device IDs (for security)
ALLOWED_DEVICES = ['SCALE-L01', 'SCALE-L02', 'SCALE-TEST']


@frappe.whitelist(allow_guest=False)
def submit_weight_reading(barrel_serial, gross_weight, device_id, tara_weight=None):
    """Submit a weight reading from a scale device.

    Args:
        barrel_serial (str): Barrel serial number (e.g., 'JAR0001261-1-C1-001')
        gross_weight (float): Weight in kg
        device_id (str): Device identifier (must be in ALLOWED_DEVICES)
        tara_weight (float, optional): Tara weight in kg

    Returns:
        dict: Status with submission details or error message

    Raises:
        frappe.PermissionError: If device not allowed
        frappe.ValidationError: If data invalid
    """
    try:
        # Validate device_id
        if device_id not in ALLOWED_DEVICES:
            logger.warning(f"Weight submission rejected: unknown device {device_id}")
            frappe.throw(
                _("Device {0} is not authorized").format(device_id),
                frappe.PermissionError
            )

        # Validate inputs
        if not barrel_serial:
            frappe.throw(_("Barrel serial is required"), frappe.ValidationError)

        if not gross_weight or float(gross_weight) <= 0:
            frappe.throw(_("Gross weight must be positive"), frappe.ValidationError)

        gross_weight = float(gross_weight)
        if tara_weight:
            tara_weight = float(tara_weight)

        # Validate weight range
        if gross_weight < 0.5 or gross_weight > 500:
            frappe.throw(
                _("Weight {0} kg is out of range (0.5-500 kg)").format(gross_weight),
                frappe.ValidationError
            )

        timestamp = now()

        # Call amb_w_tds.api.batch_api.receive_weight internally
        try:
            result = frappe.call(
                'amb_w_tds.api.batch_api.receive_weight',
                barrel_serial=barrel_serial,
                gross_weight=gross_weight,
                device_id=device_id,
                tara_weight=tara_weight
            )
        except Exception as e:
            logger.error(f"amb_w_tds API call failed: {e}")
            # Continue to log locally even if external API fails

        # Log the weight reading
        log_weight_reading(
            barrel_serial=barrel_serial,
            gross_weight=gross_weight,
            device_id=device_id,
            tara_weight=tara_weight,
            timestamp=timestamp
        )

        # Send Raven notification to iot-lab channel
        _send_raven_notification(barrel_serial, gross_weight, device_id)

        return {
            'status': 'success',
            'barrel_serial': barrel_serial,
            'weight': gross_weight,
            'device_id': device_id,
            'timestamp': timestamp
        }

    except frappe.ValidationError:
        raise
    except frappe.PermissionError:
        raise
    except Exception as e:
        logger.error(f"submit_weight_reading error: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }


def log_weight_reading(barrel_serial, gross_weight, device_id, tara_weight=None, timestamp=None):
    """Log weight reading to database.

    Creates or updates AMB Weight Reading Log document.

    Args:
        barrel_serial: Barrel serial number
        gross_weight: Weight in kg
        device_id: Device identifier
        tara_weight: Tara weight if applicable
        timestamp: Reading timestamp
    """
    try:
        # Try to create weight reading log
        doc = frappe.get_doc({
            'doctype': 'AMB Weight Reading Log',
            'barrel_serial': barrel_serial,
            'gross_weight': gross_weight,
            'device_id': device_id,
            'reading_timestamp': timestamp or now(),
        })

        if tara_weight:
            doc.tara_weight = tara_weight

        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        logger.info(f"Weight reading logged: {barrel_serial} = {gross_weight} kg")

    except frappe.DoesNotExistError:
        # Document type doesn't exist, log to frappe err log
        logger.info(
            f"Weight reading (no log doc): {barrel_serial} = {gross_weight} kg "
            f"from {device_id}"
        )
    except Exception as e:
        logger.warning(f"Failed to log weight reading: {e}")


def _send_raven_notification(barrel_serial, weight, device_id):
    """Send Raven notification on successful weight capture.

    Args:
        barrel_serial: Barrel serial number
        weight: Weight in kg
        device_id: Device identifier
    """
    try:
        message = f"Weight captured: {barrel_serial} = {weight} kg (Device: {device_id})"

        # Call Raven API to send message
        raven_url = frappe.db.get_single_value('Raven Settings', 'webhook_url')

        if raven_url:
            frappe.get_doc({
                'doctype': 'Raven Message',
                'channel': 'iot-lab',
                'text': message,
                'send_after': None
            }).insert(ignore_permissions=True)
            frappe.db.commit()
        else:
            # Fallback: use raven_ai_agent send_message
            frappe.call(
                'raven_ai_agent.raven_ai_agent.api.send_raven_message',
                channel='iot-lab',
                text=message
            )

        logger.info(f"Raven notification sent: {message}")

    except Exception as e:
        logger.warning(f"Failed to send Raven notification: {e}")


@frappe.whitelist(allow_guest=False)
def get_device_config(device_id):
    """Get configuration for a scale device.

    Args:
        device_id (str): Device identifier

    Returns:
        dict: Device configuration or error

    Raises:
        frappe.PermissionError: If device not allowed
    """
    if device_id not in ALLOWED_DEVICES:
        frappe.throw(
            _("Device {0} is not authorized").format(device_id),
            frappe.PermissionError
        )

    # Return device configuration
    configs = {
        'SCALE-L01': {
            'device_id': 'SCALE-L01',
            'name': 'RPi Scale Station 01',
            'location': 'AMB Manufacturing Floor',
            'min_weight': 0.5,
            'max_weight': 500,
            'tolerance': 0.1,
            'serial_port': '/dev/ttyUSB0',
            'baud_rate': 9600,
            'enabled': True
        },
        'SCALE-L02': {
            'device_id': 'SCALE-L02',
            'name': 'RPi Scale Station 02',
            'location': 'AMB Warehouse',
            'min_weight': 0.5,
            'max_weight': 500,
            'tolerance': 0.1,
            'serial_port': '/dev/ttyUSB1',
            'baud_rate': 9600,
            'enabled': True
        },
        'SCALE-TEST': {
            'device_id': 'SCALE-TEST',
            'name': 'Test Scale',
            'location': 'Test Lab',
            'min_weight': 0.1,
            'max_weight': 100,
            'tolerance': 0.05,
            'enabled': True
        }
    }

    return configs.get(device_id, {})


@frappe.whitelist(allow_guest=False)
def validate_barrel_serial(serial):
    """Validate if a barrel serial exists in the system.

    Checks the Container Barrels child table for the serial.

    Args:
        serial (str): Barrel serial to validate

    Returns:
        dict: Validation result with barrel info

    Raises:
        frappe.ValidationError: If serial format invalid
    """
    import re

    if not serial:
        return {
            'valid': False,
            'message': 'Serial is required'
        }

    serial = serial.strip().upper()

    # Validate format
    pattern = r'^[A-Z]{3}[0-9]+-[0-9]+-C[0-9]+-[0-9]+$'
    if not re.match(pattern, serial):
        return {
            'valid': False,
            'message': 'Invalid serial format. Expected: JAR0001261-1-C1-001'
        }

    try:
        # Check if barrel exists in Container Barrels child table
        # This queries the AMB Batch child table for Container Barrels
        barrel = frappe.db.sql("""
            SELECT
                cb.name as barrel_name,
                cb.parent as batch_no,
                cb.idx as barrel_index,
                cb.gross_weight,
                cb.tara_weight,
                cb.net_weight,
                cb.status
            FROM
                `tabContainer Barrels` cb
            WHERE
                cb.barrel_serial = %s
            LIMIT 1
        """, (serial,), as_dict=True)

        if barrel:
            return {
                'valid': True,
                'barrel_serial': serial,
                'parent_batch': barrel[0].get('batch_no'),
                'barrel_index': barrel[0].get('barrel_index'),
                'current_weight': barrel[0].get('net_weight') or barrel[0].get('gross_weight'),
                'status': barrel[0].get('status', 'Unknown')
            }

        # Also check AMB Batch directly for the serial in naming
        batch = frappe.db.exists('AMB Batch', {'name': ['like', f'%{serial}%']})

        if batch:
            return {
                'valid': True,
                'barrel_serial': serial,
                'parent_batch': batch,
                'message': 'Serial found in batch'
            }

        # Serial format is valid but not found in database
        return {
            'valid': False,
            'barrel_serial': serial,
            'message': 'Barrel serial not found in system'
        }

    except Exception as e:
        logger.warning(f"validate_barrel_serial error: {e}")
        # Return valid on database errors to avoid blocking operations
        return {
            'valid': True,
            'barrel_serial': serial,
            'message': 'Validation skipped due to database error'
        }


@frappe.whitelist(allow_guest=False)
def get_weight_history(barrel_serial=None, device_id=None, limit=50):
    """Get weight reading history.

    Args:
        barrel_serial (str, optional): Filter by barrel serial
        device_id (str, optional): Filter by device
        limit (int): Maximum records to return

    Returns:
        dict: List of weight readings
    """
    conditions = []
    values = []

    if barrel_serial:
        conditions.append("barrel_serial = %s")
        values.append(barrel_serial)

    if device_id:
        conditions.append("device_id = %s")
        values.append(device_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT
            name,
            barrel_serial,
            gross_weight,
            tara_weight,
            device_id,
            reading_timestamp
        FROM
            `tabAMB Weight Reading Log`
        WHERE
            {where_clause}
        ORDER BY
            reading_timestamp DESC
        LIMIT %s
    """
    values.append(limit)

    try:
        readings = frappe.db.sql(query, values, as_dict=True)
        return {
            'status': 'success',
            'count': len(readings),
            'readings': readings
        }
    except Exception as e:
        logger.error(f"get_weight_history error: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }

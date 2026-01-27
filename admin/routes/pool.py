from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from admin.auth import login_required
from admin import db

bp = Blueprint('pool', __name__, url_prefix='/pool')


@bp.route('/')
@login_required
def index():
    """Shared pool dashboard"""
    stats = db.get_shared_pool_stats()
    return render_template('pool/index.html', stats=stats)


@bp.route('/workers')
@login_required
def workers():
    """List of all workers"""
    workers = db.get_all_workers()
    return render_template('pool/workers.html', workers=workers)


@bp.route('/workers/<int:worker_id>')
@login_required
def worker_detail(worker_id):
    """Worker details"""
    worker = db.get_worker_by_id(worker_id)
    if not worker:
        flash('Worker not found', 'error')
        return redirect(url_for('pool.workers'))

    assignments = db.get_worker_assignments(worker_id)
    return render_template('pool/worker_detail.html', worker=worker, assignments=assignments)


@bp.route('/workers/add', methods=['GET', 'POST'])
@login_required
def add_worker():
    """Add new worker"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        session_string = request.form.get('session_string', '').strip()
        phone = request.form.get('phone', '').strip() or None
        max_groups = int(request.form.get('max_groups', 50))

        if not name or not session_string:
            flash('Name and session string are required', 'error')
            return render_template('pool/add_worker.html')

        try:
            worker = db.create_worker(
                name=name,
                session_string=session_string,
                phone=phone,
                max_groups=max_groups,
            )
            flash(f'Worker "{worker.name}" created successfully', 'success')
            return redirect(url_for('pool.workers'))
        except Exception as e:
            flash(f'Error creating worker: {e}', 'error')

    return render_template('pool/add_worker.html')


@bp.route('/groups')
@login_required
def groups():
    """List of monitored groups"""
    groups = db.get_monitored_groups()
    return render_template('pool/groups.html', groups=groups)


@bp.route('/groups/<telegram_group_id>')
@login_required
def group_detail(telegram_group_id):
    """Group chat history"""
    try:
        telegram_group_id = int(telegram_group_id)
    except ValueError:
        flash('Invalid group ID', 'error')
        return redirect(url_for('pool.groups'))

    info = db.get_group_info(telegram_group_id)
    if not info:
        flash('Group not found', 'error')
        return redirect(url_for('pool.groups'))

    messages = db.get_group_chat_history(telegram_group_id)
    return render_template('pool/group_detail.html', info=info, messages=messages)


@bp.route('/deliveries')
@login_required
def deliveries():
    """Recent order deliveries"""
    deliveries = db.get_recent_deliveries()
    return render_template('pool/deliveries.html', deliveries=deliveries)


# ============ API endpoints ============

@bp.route('/api/workers/<int:worker_id>/toggle', methods=['POST'])
@login_required
def toggle_worker(worker_id):
    """Toggle worker active status"""
    worker = db.get_worker_by_id(worker_id)
    if not worker:
        return jsonify({'error': 'Worker not found'}), 404

    new_status = not worker.is_active
    db.update_worker(worker_id, is_active=new_status)
    return jsonify({'success': True, 'is_active': new_status})


@bp.route('/api/workers/<int:worker_id>', methods=['DELETE'])
@login_required
def delete_worker(worker_id):
    """Delete worker"""
    if db.delete_worker(worker_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Worker not found'}), 404


@bp.route('/api/redistribute', methods=['POST'])
@login_required
def redistribute_groups():
    """Redistribute groups across workers"""
    try:
        import asyncio
        from userbot.shared_pool import GroupDistributor
        asyncio.run(GroupDistributor.redistribute_groups())
        return jsonify({'success': True, 'message': 'Groups redistributed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

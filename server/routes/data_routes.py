from flask import Blueprint, request, jsonify

bp = Blueprint('data_routes', __name__)

@bp.route('/api/data', methods=['POST'])
def receive_data():
    data = request.get_json()
    # Placeholder for point cloud and volume calculation
    return jsonify({"status": "ok"})
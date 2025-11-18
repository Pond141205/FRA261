from flask import Blueprint, request, jsonify
import requests
import os
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('data_routes', __name__)

# Configuration สำหรับ remote database
REMOTE_DB_CONFIG = {
    'base_url': os.getenv('REMOTE_DB_URL', 'http://192.168.1.100:5000'),
    'api_key': os.getenv('REMOTE_API_KEY', 'your-secret-api-key-123')
}

class RemoteDBClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {'X-API-Key': api_key, 'Content-Type': 'application/json'}
    
    def get_tables(self):
        """ดึงรายการ tables จาก remote database"""
        try:
            response = requests.get(f"{self.base_url}/api/tables", headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json().get('tables', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting tables from remote DB: {e}")
            return []
    
    def execute_query(self, query: str, params=None):
        """execute query บน remote database"""
        try:
            if params is None:
                params = []
            data = {'query': query, 'params': params}
            response = requests.post(f"{self.base_url}/api/query", 
                                   json=data, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error executing query on remote DB: {e}")
            return {'error': str(e), 'data': [], 'columns': []}
    
    def get_table_data(self, table_name: str, limit: int = 100, offset: int = 0):
        """ดึงข้อมูลจาก remote table"""
        try:
            params = {'limit': limit, 'offset': offset}
            response = requests.get(f"{self.base_url}/api/tables/{table_name}/data",
                                  headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting table data from remote DB: {e}")
            return {'error': str(e), 'data': [], 'columns': []}
    
    def get_table_schema(self, table_name: str):
        """ดึง schema ของ remote table"""
        try:
            response = requests.get(f"{self.base_url}/api/tables/{table_name}/schema",
                                  headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting table schema from remote DB: {e}")
            return {'error': str(e)}
    
    def get_database_stats(self):
        """ดึง statistics ของ remote database"""
        try:
            response = requests.get(f"{self.base_url}/api/stats", 
                                  headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting stats from remote DB: {e}")
            return {'error': str(e)}

# สร้าง client instance
remote_db_client = RemoteDBClient(REMOTE_DB_CONFIG['base_url'], REMOTE_DB_CONFIG['api_key'])

@bp.route('/api/data', methods=['POST'])
def receive_data():
    data = request.get_json()
    # Placeholder for point cloud and volume calculation
    return jsonify({"status": "ok"})

# Endpoint ใหม่สำหรับ remote SQLCipher database
@bp.route('/api/remote/tables', methods=['GET'])
def get_remote_tables():
    """ดึงรายการ tables จาก remote SQLCipher database"""
    try:
        tables = remote_db_client.get_tables()
        return jsonify({'tables': tables})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/remote/tables/<table_name>', methods=['GET'])
def get_remote_table_data(table_name):
    """ดึงข้อมูลจาก remote table"""
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        data = remote_db_client.get_table_data(table_name, limit, offset)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/remote/tables/<table_name>/schema', methods=['GET'])
def get_remote_table_schema(table_name):
    """ดึง schema ของ remote table"""
    try:
        schema = remote_db_client.get_table_schema(table_name)
        return jsonify(schema)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/remote/query', methods=['POST'])
def execute_remote_query():
    """execute query บน remote database"""
    try:
        query_data = request.get_json()
        query = query_data.get('query')
        params = query_data.get('params', [])
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
            
        result = remote_db_client.execute_query(query, params)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/remote/stats', methods=['GET'])
def get_remote_stats():
    """ดึง statistics ของ remote database"""
    try:
        stats = remote_db_client.get_database_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/remote/health', methods=['GET'])
def check_remote_health():
    """ตรวจสอบการเชื่อมต่อกับ remote database"""
    try:
        tables = remote_db_client.get_tables()
        return jsonify({
            'status': 'healthy',
            'connected': True,
            'table_count': len(tables)
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'connected': False,
            'error': str(e)
        }), 503

# Endpoint สำหรับทดสอบ
@bp.route('/api/remote/test', methods=['GET'])
def test_remote_connection():
    """ทดสอบการเชื่อมต่อและแสดงข้อมูลตัวอย่าง"""
    try:
        # ดึงรายการ tables
        tables = remote_db_client.get_tables()
        
        # ถ้ามี table ให้ดึงข้อมูลตัวอย่างจาก table แรก
        sample_data = {}
        if tables:
            first_table = tables[0]
            sample_data = remote_db_client.get_table_data(first_table, limit=5)
        
        return jsonify({
            'connected': True,
            'tables': tables,
            'sample_data': sample_data
        })
    except Exception as e:
        return jsonify({
            'connected': False,
            'error': str(e)
        }), 500



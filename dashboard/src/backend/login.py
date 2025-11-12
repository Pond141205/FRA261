from flask import Flask, render_template, request, redirect, url_for, session
import os

# กำหนด path ให้ถูกต้อง
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..', 'static'))

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = "your_secret_key_change_this"

# ข้อมูล admin ตัวอย่าง
admins = {
    "a": "1",
    "testuser": "password"
}

def validate_input(username, password):
    """ตรวจสอบความถูกต้องของข้อมูล input"""
    if not username or not password:
        return False
    
    return True

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        print(f"Username: {username}, Password: {password}")  # Debug
        
        # ตรวจสอบ input
        if not validate_input(username, password):
            print("Validation failed")
            return render_template('admin_login.html')
        
        # ตรวจสอบ username/password
        if username in admins and admins[username] == password:
            print(f"Login success: {username}")
            session['admin_username'] = username
            session['is_admin'] = True
            return redirect(url_for('dashboard'))
        else:
            print(f"Login failed: {username} not in admins or password wrong")
            return render_template('admin_login.html')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def dashboard():
    """หน้า dashboard"""
    print(f"Session: {session}")  # Debug
    
    if 'is_admin' not in session or not session['is_admin']:
        print("Not logged in")
        return redirect(url_for('admin_login'))
    
    username = session.get('admin_username', 'Admin')
    print(f"Dashboard accessed by: {username}")
    return render_template('admin_dashboard.html', username=username)

@app.route('/admin/logout')
def logout():
    """ออกจากระบบ"""
    session.clear()
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    print(f"Templates folder: {template_dir}")
    print(f"Static folder: {static_dir}")
    app.run(debug=True)

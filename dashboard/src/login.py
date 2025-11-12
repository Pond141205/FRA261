from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__, static_folder="src/static", template_folder="src/templates")

app = Flask(__name__)
app.secret_key = 'my_secret_key'

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None  # ตัวแปรสำหรับเก็บข้อความผิดพลาด

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == 'admin' and password == '1234':
            session['admin_logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            error = "❌ ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง"

    # ส่งค่า error ไปให้ template (ถ้าไม่มีจะเป็น None)
    return render_template('admin_login.html', error=error)


@app.route('/admin/dashboard')
def dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    return render_template('dashboard.html')


@app.route('/admin/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))


if __name__ == '__main__':
    app.run(debug=True)

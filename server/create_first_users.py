from app import db, User, app

with app.app_context():
    # สร้าง Admin คนแรก
    admin = User(username="admin1", role="admin")
    admin.set_password("Admin@123")

    # สร้าง User ตัวอย่าง
    user = User(username="user1", role="user")
    user.set_password("User@123")

    # เพิ่มลง session
    db.session.add(admin)
    db.session.add(user)

    # บันทึกลง DB
    db.session.commit()

    print("Admin และ User ตัวอย่างสร้างเรียบร้อยแล้ว!")

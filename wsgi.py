from app import app, db, Admin, bcrypt

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if not Admin.query.filter_by(username='admin').first():
            hashed_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            new_admin = Admin(username='admin', password_hash=hashed_pw)
            db.session.add(new_admin)
            db.session.commit()
    app.run()

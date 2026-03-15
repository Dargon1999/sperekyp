from app import app, db, Admin, bcrypt

if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            if not Admin.query.filter_by(username='BossDargon').first():
                hashed_pw = bcrypt.generate_password_hash('Sanya0811').decode('utf-8')
                new_admin = Admin(username='BossDargon', password_hash=hashed_pw)
                db.session.add(new_admin)
                db.session.commit()
        except Exception as e:
            import logging
            logging.error(f"WSGI Init Error: {e}")
    app.run()

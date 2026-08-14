from app import app, db, Employee, Shift

with app.app_context():
    db.drop_all()
    db.create_all()
    staff = [
        Employee(employee_no='0000', name='仲村 日向', role='employee'),
        Employee(employee_no='1001', name='青木 美咲', role='employee', preferred=True),
        Employee(employee_no='1002', name='高木 健', role='employee'),
        Employee(employee_no='1003', name='森本 葵', role='employee', preferred=True),
        Employee(employee_no='9000', name='デモ店長', role='admin'),
    ]
    db.session.add_all(staff)
    db.session.flush()
    demo = [
        Shift(employee_id=staff[1].id, date='2026-08-15', start='08:00', end='15:00'),
        Shift(employee_id=staff[0].id, date='2026-08-15', start='10:00', end='15:00'),
        Shift(employee_id=staff[2].id, date='2026-08-15', start='11:00', end='17:00'),
        Shift(employee_id=staff[3].id, date='2026-08-15', start='15:00', end='21:00'),
    ]
    db.session.add_all(demo)
    db.session.commit()
    print('ShiftEase demo database seeded.')

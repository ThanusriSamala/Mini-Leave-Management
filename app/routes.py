from flask import jsonify, request, render_template, redirect, url_for, flash
from .db import get_db
from .models import calculate_days

def register_routes(app):
    # ----------- UI PAGES -----------
    @app.get("/")
    def home():
        db = get_db()
        emp_count = db.execute("SELECT COUNT(*) as c FROM employees").fetchone()["c"]
        pending = db.execute("SELECT COUNT(*) as c FROM leaves WHERE status='PENDING'").fetchone()["c"]
        approved = db.execute("SELECT COUNT(*) as c FROM leaves WHERE status='APPROVED'").fetchone()["c"]
        return render_template("dashboard.html", emp_count=emp_count, pending=pending, approved=approved)

    @app.get("/employees")
    def employees_page():
        db = get_db()
        rows = db.execute("SELECT * FROM employees ORDER BY id DESC").fetchall()
        return render_template("employees.html", employees=rows)

    @app.post("/employees")
    def add_employee_form():
        name = request.form["name"]
        email = request.form["email"]
        department = request.form["department"]
        joining_date = request.form["joining_date"]
        allowance = int(request.form.get("annual_leave_allowance", 24))
        db = get_db()
        db.execute(
            "INSERT INTO employees(name,email,department,joining_date,annual_leave_allowance,remaining_leave) VALUES (?,?,?,?,?,?)",
            (name, email, department, joining_date, allowance, allowance)
        )
        db.commit()
        flash("Employee added", "success")
        return redirect(url_for("employees_page"))

    @app.get("/leaves")
    def leaves_page():
        db = get_db()
        status = request.args.get("status")
        if status:
            rows = db.execute(
                "SELECT l.*, e.name as employee_name FROM leaves l JOIN employees e ON e.id=l.employee_id WHERE status=? ORDER BY l.id DESC",
                (status,)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT l.*, e.name as employee_name FROM leaves l JOIN employees e ON e.id=l.employee_id ORDER BY l.id DESC"
            ).fetchall()
        employees = db.execute("SELECT id, name FROM employees ORDER BY name").fetchall()
        return render_template("leaves.html", leaves=rows, employees=employees, status=status)

    @app.post("/leaves")
    def apply_leave_form():
        employee_id = int(request.form["employee_id"])
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]
        leave_type = request.form.get("leave_type", "ANNUAL")
        reason = request.form.get("reason", "")
        days = calculate_days(start_date, end_date)
        db = get_db()
        cur = db.execute(
            "INSERT INTO leaves(employee_id,start_date,end_date,days,leave_type,status,reason) VALUES (?,?,?,?,?,'PENDING',?)",
            (employee_id, start_date, end_date, days, leave_type, reason)
        )
        leave_id = cur.lastrowid
        # Log APPLY transaction (no balance change yet)
        emp = db.execute("SELECT remaining_leave FROM employees WHERE id=?", (employee_id,)).fetchone()
        db.execute(
            "INSERT INTO leave_transactions(employee_id, leave_id, delta_days, balance_after, action, note) VALUES (?,?,?,?,?,?)",
            (employee_id, leave_id, 0, emp['remaining_leave'], 'APPLY', 'Leave applied')
        )
        db.commit()
        flash("Leave applied", "success")
        return redirect(url_for("leaves_page"))

    @app.post("/leaves/<int:leave_id>/approve")
    def approve_leave_form(leave_id):
        db = get_db()
        leave = db.execute("SELECT * FROM leaves WHERE id=?", (leave_id,)).fetchone()
        if not leave:
            flash("Leave not found", "danger")
            return redirect(url_for("leaves_page"))
        if leave["status"] != "PENDING":
            flash("Only pending leaves can be approved", "warning")
            return redirect(url_for("leaves_page"))
        # Check balance
        emp = db.execute("SELECT id, remaining_leave FROM employees WHERE id=?", (leave["employee_id"],)).fetchone()
        if emp["remaining_leave"] < leave["days"] and leave["leave_type"] == "ANNUAL":
            flash("Insufficient leave balance", "danger")
            return redirect(url_for("leaves_page"))
        # Approve
        db.execute("UPDATE leaves SET status='APPROVED', updated_at=datetime('now') WHERE id=?", (leave_id,))
        delta = -leave["days"] if leave["leave_type"] == "ANNUAL" else 0
        new_balance = emp["remaining_leave"] + delta
        if delta != 0:
            db.execute("UPDATE employees SET remaining_leave=? WHERE id=?", (new_balance, emp["id"]))
        db.execute(
            "INSERT INTO leave_transactions(employee_id, leave_id, delta_days, balance_after, action, note) VALUES (?,?,?,?,?,?)",
            (emp["id"], leave_id, delta, new_balance, 'APPROVE', 'Leave approved')
        )
        db.commit()
        flash("Leave approved", "success")
        return redirect(url_for("leaves_page"))

    @app.post("/leaves/<int:leave_id>/reject")
    def reject_leave_form(leave_id):
        db = get_db()
        leave = db.execute("SELECT * FROM leaves WHERE id=?", (leave_id,)).fetchone()
        if not leave:
            flash("Leave not found", "danger")
            return redirect(url_for("leaves_page"))
        if leave["status"] != "PENDING":
            flash("Only pending leaves can be rejected", "warning")
            return redirect(url_for("leaves_page"))
        db.execute("UPDATE leaves SET status='REJECTED', updated_at=datetime('now') WHERE id=?", (leave_id,))
        emp = db.execute("SELECT id, remaining_leave FROM employees WHERE id=?", (leave["employee_id"],)).fetchone()
        db.execute(
            "INSERT INTO leave_transactions(employee_id, leave_id, delta_days, balance_after, action, note) VALUES (?,?,?,?,?,?)",
            (emp["id"], leave_id, 0, emp["remaining_leave"], 'REJECT', 'Leave rejected')
        )
        db.commit()
        flash("Leave rejected", "success")
        return redirect(url_for("leaves_page"))

    # ----------- REST API -----------
    @app.get("/api/employees")
    def api_get_employees():
        db = get_db()
        rows = db.execute("SELECT * FROM employees ORDER BY id DESC").fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/employees")
    def api_add_employee():
        data = request.get_json(force=True)
        required = ["name","email","department","joining_date"]
        for k in required:
            if k not in data:
                return {"error": f"Missing field: {k}"}, 400
        allowance = int(data.get("annual_leave_allowance", 24))
        db = get_db()
        try:
            db.execute(
                "INSERT INTO employees(name,email,department,joining_date,annual_leave_allowance,remaining_leave) VALUES (?,?,?,?,?,?)",
                (data["name"], data["email"], data["department"], data["joining_date"], allowance, allowance)
            )
            db.commit()
        except Exception as e:
            return {"error": str(e)}, 400
        return {"message":"Employee created"}, 201

    @app.get("/api/employees/<int:emp_id>")
    def api_get_employee(emp_id):
        db = get_db()
        r = db.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
        if not r:
            return {"error": "Not found"}, 404
        return dict(r), 200

    @app.get("/api/employees/<int:emp_id>/balance")
    def api_get_balance(emp_id):
        db = get_db()
        r = db.execute("SELECT remaining_leave FROM employees WHERE id=?", (emp_id,)).fetchone()
        if not r:
            return {"error":"Not found"}, 404
        return {"employee_id": emp_id, "remaining_leave": r["remaining_leave"]}

    @app.post("/api/leaves")
    def api_apply_leave():
        data = request.get_json(force=True)
        required = ["employee_id","start_date","end_date"]
        for k in required:
            if k not in data:
                return {"error": f"Missing field: {k}"}, 400
        days = calculate_days(data["start_date"], data["end_date"])
        leave_type = data.get("leave_type","ANNUAL")
        reason = data.get("reason","")
        db = get_db()
        cur = db.execute(
            "INSERT INTO leaves(employee_id,start_date,end_date,days,leave_type,status,reason) VALUES (?,?,?,?,?,'PENDING',?)",
            (data["employee_id"], data["start_date"], data["end_date"], days, leave_type, reason)
        )
        leave_id = cur.lastrowid
        emp = db.execute("SELECT remaining_leave FROM employees WHERE id=?", (data["employee_id"],)).fetchone()
        db.execute(
            "INSERT INTO leave_transactions(employee_id, leave_id, delta_days, balance_after, action, note) VALUES (?,?,?,?,?,?)",
            (data["employee_id"], leave_id, 0, emp['remaining_leave'], 'APPLY', 'Leave applied')
        )
        db.commit()
        return {"message":"Leave applied","leave_id":leave_id,"days":days}, 201

    @app.post("/api/leaves/<int:leave_id>/approve")
    def api_approve_leave(leave_id):
        db = get_db()
        leave = db.execute("SELECT * FROM leaves WHERE id=?", (leave_id,)).fetchone()
        if not leave:
            return {"error":"Not found"}, 404
        if leave["status"] != "PENDING":
            return {"error":"Only pending leaves can be approved"}, 400
        emp = db.execute("SELECT id, remaining_leave FROM employees WHERE id=?", (leave["employee_id"],)).fetchone()
        if leave["leave_type"] == "ANNUAL" and emp["remaining_leave"] < leave["days"]:
            return {"error":"Insufficient leave balance"}, 400
        db.execute("UPDATE leaves SET status='APPROVED', updated_at=datetime('now') WHERE id=?", (leave_id,))
        delta = -leave["days"] if leave["leave_type"] == "ANNUAL" else 0
        new_balance = emp["remaining_leave"] + delta
        if delta != 0:
            db.execute("UPDATE employees SET remaining_leave=? WHERE id=?", (new_balance, emp["id"]))
        db.execute(
            "INSERT INTO leave_transactions(employee_id, leave_id, delta_days, balance_after, action, note) VALUES (?,?,?,?,?,?)",
            (emp["id"], leave_id, delta, new_balance, 'APPROVE', 'Leave approved')
        )
        db.commit()
        return {"message":"Approved","new_balance":new_balance}, 200

    @app.post("/api/leaves/<int:leave_id>/reject")
    def api_reject_leave(leave_id):
        db = get_db()
        leave = db.execute("SELECT * FROM leaves WHERE id=?", (leave_id,)).fetchone()
        if not leave:
            return {"error":"Not found"}, 404
        if leave["status"] != "PENDING":
            return {"error":"Only pending leaves can be rejected"}, 400
        db.execute("UPDATE leaves SET status='REJECTED', updated_at=datetime('now') WHERE id=?", (leave_id,))
        emp = db.execute("SELECT id, remaining_leave FROM employees WHERE id=?", (leave["employee_id"],)).fetchone()
        db.execute(
            "INSERT INTO leave_transactions(employee_id, leave_id, delta_days, balance_after, action, note) VALUES (?,?,?,?,?,?)",
            (emp["id"], leave_id, 0, emp["remaining_leave"], 'REJECT', 'Leave rejected')
        )
        db.commit()
        return {"message":"Rejected"}, 200

    @app.get("/api/leaves")
    def api_list_leaves():
        db = get_db()
        q = "SELECT l.*, e.name as employee_name FROM leaves l JOIN employees e ON e.id=l.employee_id"
        params = []
        status = request.args.get("status")
        emp_id = request.args.get("employee_id")
        conds = []
        if status:
            conds.append("l.status=?")
            params.append(status)
        if emp_id:
            conds.append("l.employee_id=?")
            params.append(emp_id)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY l.id DESC"
        rows = get_db().execute(q, params).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/transactions/<int:emp_id>")
    def api_transactions(emp_id):
        db = get_db()
        rows = db.execute("SELECT * FROM leave_transactions WHERE employee_id=? ORDER BY id DESC", (emp_id,)).fetchall()
        return jsonify([dict(r) for r in rows])

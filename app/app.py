
import os
from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]


def get_connection():
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "postgres"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        row_factory=dict_row,
        connect_timeout=5,
    )


def initialize_database():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(200) NOT NULL,
                    author VARCHAR(150) NOT NULL,
                    category VARCHAR(100) NOT NULL DEFAULT 'Chưa phân loại',
                    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS readers (
                    id SERIAL PRIMARY KEY,
                    full_name VARCHAR(150) NOT NULL,
                    email VARCHAR(254) UNIQUE,
                    phone VARCHAR(30),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS loans (
                    id SERIAL PRIMARY KEY,
                    reader_id INTEGER NOT NULL
                        REFERENCES readers(id) ON DELETE RESTRICT,
                    book_id INTEGER NOT NULL
                        REFERENCES books(id) ON DELETE RESTRICT,
                    borrowed_at DATE NOT NULL DEFAULT CURRENT_DATE,
                    due_date DATE NOT NULL,
                    returned_at DATE,
                    status VARCHAR(20) NOT NULL DEFAULT 'borrowed'
                        CHECK (status IN ('borrowed', 'returned')),
                    CHECK (due_date >= borrowed_at),
                    CHECK (
                        (status = 'borrowed' AND returned_at IS NULL)
                        OR
                        (status = 'returned' AND returned_at IS NOT NULL)
                    )
                )
            """)
            cur.execute("SELECT COUNT(*) AS total FROM books")
            if cur.fetchone()["total"] == 0:
                cur.execute("""
                    INSERT INTO books (title, author, category, quantity)
                    VALUES
                        ('Dế Mèn Phiêu Lưu Ký', 'Tô Hoài', 'Văn học', 5),
                        ('Lão Hạc', 'Nam Cao', 'Văn học', 3),
                        ('Clean Code', 'Robert C. Martin', 'Công nghệ', 2)
                """)


# Khởi tạo bảng khi ứng dụng được nạp bởi Gunicorn.
initialize_database()

@app.route("/health")
def health():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"status": "healthy"}, 200
    except Exception:
        app.logger.exception("Health check failed")
        return {"status": "unhealthy"}, 503

@app.route("/")
def index():
    keyword = request.args.get("q", "").strip()

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, title, author, category, quantity
                    FROM books
                    WHERE title ILIKE %s
                       OR author ILIKE %s
                       OR category ILIKE %s
                    ORDER BY id
                """, (
                    f"%{keyword}%",
                    f"%{keyword}%",
                    f"%{keyword}%",
                ))
                books = cur.fetchall()

        return render_template("index.html", books=books, keyword=keyword)
    except Exception:
        app.logger.exception("Cannot load books")
        return "Không thể tải danh sách sách. Vui lòng thử lại.", 503


@app.route("/books", methods=["POST"])
def add_book():
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    category = request.form.get("category", "").strip() or "Chưa phân loại"

    try:
        quantity = int(request.form.get("quantity", "1"))
    except ValueError:
        flash("Số lượng phải là số nguyên.", "error")
        return redirect(url_for("index"))

    if not title or not author:
        flash("Vui lòng nhập tên sách và tác giả.", "error")
    elif quantity < 0:
        flash("Số lượng không được âm.", "error")
    else:
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO books (title, author, category, quantity)
                        VALUES (%s, %s, %s, %s)
                    """, (title, author, category, quantity))
            flash("Đã thêm sách thành công.", "success")
        except Exception:
            app.logger.exception("Cannot add book")
            flash("Không thể thêm sách.", "error")

    return redirect(url_for("index"))


@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
def edit_book(book_id):
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip() or "Chưa phân loại"

        try:
            quantity = int(request.form.get("quantity", "1"))
        except ValueError:
            flash("Số lượng phải là số nguyên.", "error")
            return redirect(url_for("edit_book", book_id=book_id))

        if not title or not author:
            flash("Tên sách và tác giả không được để trống.", "error")
            return redirect(url_for("edit_book", book_id=book_id))

        if quantity < 0:
            flash("Số lượng không được âm.", "error")
            return redirect(url_for("edit_book", book_id=book_id))

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE books
                        SET title = %s,
                            author = %s,
                            category = %s,
                            quantity = %s
                        WHERE id = %s
                    """, (title, author, category, quantity, book_id))

                    if cur.rowcount == 0:
                        flash("Không tìm thấy sách.", "error")
                        return redirect(url_for("index"))

            flash("Đã cập nhật thông tin sách.", "success")
            return redirect(url_for("index"))
        except Exception:
            app.logger.exception("Cannot update book")
            flash("Không thể cập nhật sách.", "error")
            return redirect(url_for("edit_book", book_id=book_id))

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, title, author, category, quantity
                    FROM books
                    WHERE id = %s
                """, (book_id,))
                book = cur.fetchone()

        if book is None:
            return "Không tìm thấy sách.", 404

        return render_template("edit_book.html", book=book)
    except Exception:
        app.logger.exception("Cannot open edit page")
        return "Không thể mở trang sửa sách.", 503


@app.route("/books/<int:book_id>/delete", methods=["POST"])
def delete_book(book_id):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM books WHERE id = %s", (book_id,))
                deleted = cur.rowcount

        if deleted:
            flash("Đã xóa sách.", "success")
        else:
            flash("Không tìm thấy sách.", "error")
    except Exception:
        app.logger.exception("Cannot delete book")
        flash("Không thể xóa sách.", "error")

    return redirect(url_for("index"))

@app.route("/readers")
def readers():
    keyword = request.args.get("q", "").strip()

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, full_name, email, phone, created_at
                    FROM readers
                    WHERE full_name ILIKE %s
                       OR COALESCE(email, '') ILIKE %s
                       OR COALESCE(phone, '') ILIKE %s
                    ORDER BY id DESC
                """, (
                    f"%{keyword}%",
                    f"%{keyword}%",
                    f"%{keyword}%",
                ))
                reader_list = cur.fetchall()

        return render_template(
            "readers.html",
            readers=reader_list,
            keyword=keyword,
        )
    except Exception:
        app.logger.exception("Cannot load readers")
        return "Không thể tải danh sách độc giả.", 503


@app.route("/readers/add", methods=["POST"])
def add_reader():
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip() or None
    phone = request.form.get("phone", "").strip() or None

    if not full_name:
        flash("Vui lòng nhập họ tên độc giả.", "error")
        return redirect(url_for("readers"))

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO readers (full_name, email, phone)
                    VALUES (%s, %s, %s)
                """, (full_name, email, phone))

        flash("Đã thêm độc giả thành công.", "success")
    except psycopg.errors.UniqueViolation:
        flash("Email này đã được sử dụng.", "error")
    except Exception:
        app.logger.exception("Cannot add reader")
        flash("Không thể thêm độc giả.", "error")

    return redirect(url_for("readers"))


@app.route("/readers/<int:reader_id>/delete", methods=["POST"])
def delete_reader(reader_id):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM readers WHERE id = %s",
                    (reader_id,),
                )
                deleted = cur.rowcount

        flash(
            "Đã xóa độc giả." if deleted else "Không tìm thấy độc giả.",
            "success" if deleted else "error",
        )
    except Exception:
        app.logger.exception("Cannot delete reader")
        flash(
            "Không thể xóa độc giả. Hãy kiểm tra các giao dịch liên quan.",
            "error",
        )

    return redirect(url_for("readers"))

from datetime import date

@app.route("/loans")
def loans():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        l.id,
                        r.full_name,
                        b.title,
                        l.borrowed_at,
                        l.due_date,
                        l.returned_at,
                        l.status,
                        CASE
                            WHEN l.status = 'borrowed'
                                 AND l.due_date < CURRENT_DATE
                            THEN TRUE
                            ELSE FALSE
                        END AS overdue
                    FROM loans l
                    JOIN readers r ON r.id = l.reader_id
                    JOIN books b ON b.id = l.book_id
                    ORDER BY l.id DESC
                """)
                loan_list = cur.fetchall()

                cur.execute("""
                    SELECT id, title, quantity
                    FROM books
                    ORDER BY title
                """)
                book_list = cur.fetchall()

                cur.execute("""
                    SELECT id, full_name
                    FROM readers
                    ORDER BY full_name
                """)
                reader_list = cur.fetchall()

        return render_template(
            "loans.html",
            loans=loan_list,
            books=book_list,
            readers=reader_list,
            today=date.today().isoformat(),
        )
    except Exception:
        app.logger.exception("Cannot load loans")
        return "Không thể tải danh sách mượn/trả.", 503


@app.route("/loans/add", methods=["POST"])
def add_loan():
    try:
        reader_id = int(request.form.get("reader_id", ""))
        book_id = int(request.form.get("book_id", ""))
        due_date = date.fromisoformat(request.form.get("due_date", ""))
    except (ValueError, TypeError):
        flash("Thông tin độc giả, sách hoặc hạn trả không hợp lệ.", "error")
        return redirect(url_for("loans"))

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id
                    FROM readers
                    WHERE id = %s
                """, (reader_id,))
                if cur.fetchone() is None:
                    flash("Không tìm thấy độc giả.", "error")
                    return redirect(url_for("loans"))

                cur.execute("""
                    SELECT id, quantity
                    FROM books
                    WHERE id = %s
                    FOR UPDATE
                """, (book_id,))
                book = cur.fetchone()

                if book is None:
                    flash("Không tìm thấy sách.", "error")
                    return redirect(url_for("loans"))

                if book["quantity"] < 1:
                    flash("Sách này hiện đã hết bản có thể cho mượn.", "error")
                    return redirect(url_for("loans"))

                cur.execute("""
                    INSERT INTO loans (reader_id, book_id, due_date)
                    VALUES (%s, %s, %s)
                """, (reader_id, book_id, due_date))

                cur.execute("""
                    UPDATE books
                    SET quantity = quantity - 1
                    WHERE id = %s
                """, (book_id,))

        flash("Đã ghi nhận lượt mượn sách.", "success")

    except Exception:
        app.logger.exception("Cannot create loan")
        flash("Không thể tạo lượt mượn. Vui lòng kiểm tra dữ liệu.", "error")

    return redirect(url_for("loans"))


@app.route("/loans/<int:loan_id>/return", methods=["POST"])
def return_loan(loan_id):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, book_id, status
                    FROM loans
                    WHERE id = %s
                    FOR UPDATE
                """, (loan_id,))
                loan = cur.fetchone()

                if loan is None:
                    flash("Không tìm thấy lượt mượn.", "error")
                    return redirect(url_for("loans"))

                if loan["status"] == "returned":
                    flash("Lượt mượn này đã được trả trước đó.", "error")
                    return redirect(url_for("loans"))

                cur.execute("""
                    UPDATE loans
                    SET status = 'returned',
                        returned_at = CURRENT_DATE
                    WHERE id = %s AND status = 'borrowed'
                """, (loan_id,))

                if cur.rowcount == 1:
                    cur.execute("""
                        UPDATE books
                        SET quantity = quantity + 1
                        WHERE id = %s
                    """, (loan["book_id"],))
                else:
                    flash("Không thể cập nhật lượt trả.", "error")
                    return redirect(url_for("loans"))

        flash("Đã ghi nhận trả sách.", "success")

    except Exception:
        app.logger.exception("Cannot return loan")
        flash("Không thể ghi nhận trả sách.", "error")

    return redirect(url_for("loans"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)


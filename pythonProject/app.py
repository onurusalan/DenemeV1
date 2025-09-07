from flask import Flask, request, jsonify, render_template, session, send_file, send_from_directory, after_this_request
from flask_sqlalchemy import SQLAlchemy
import os
import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, PageBreak, Table, TableStyle, Spacer, Image
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.lib.fonts import addMapping
import google.generativeai as genai
from dotenv import load_dotenv
from reportlab.lib import colors
from datetime import datetime
from io import BytesIO
import platform

# Ortam değişkenlerini yükle
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyDBacTP1FYjR61hHBUNLCEtLAyk5vqFPiI')

app = Flask(__name__, template_folder="templates")

# Gerekli klasörleri oluştur
def create_directories():
    dirs = [
        'pythonProject/static/graphs',
        'pythonProject/static/reports',
        'templates',
        'static'
    ]
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)

create_directories()

# Font yönetimi
def setup_fonts():
    try:
        # Production ortamı için basitleştirilmiş font yönetimi
        if platform.system() == 'Darwin':
            possible_font_paths = [
                '/Library/Fonts/Arial.ttf',
                '/System/Library/Fonts/Supplemental/Arial.ttf',
                '/Library/Fonts/Arial Unicode.ttf',
                os.path.join(os.path.dirname(__file__), 'fonts', 'Arial.ttf')
            ]
            
            font_found = False
            for font_path in possible_font_paths:
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('Arial', font_path))
                    font_found = True
                    break
            
            if not font_found:
                pdfmetrics.registerFont(TTFont('Arial', 'Times-Roman'))
        else:
            # Render.com için basit font
            try:
                pdfmetrics.registerFont(TTFont('Arial', 'Helvetica'))
            except:
                pdfmetrics.registerFont(TTFont('Arial', 'Times-Roman'))
                
    except Exception as e:
        print(f"Font yükleme hatası: {str(e)}")
        pdfmetrics.registerFont(TTFont('Arial', 'Times-Roman'))

setup_fonts()

# Gemini API anahtarını ayarla
genai.configure(api_key=GEMINI_API_KEY)

# Static dosya sunumu için
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

app.secret_key = "supersecretkey"

# Güvenlik ayarları - Production için güncellenmiş
if 'RENDER' in os.environ:
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
else:
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = False
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

app.config['WTF_CSRF_ENABLED'] = False

# SQLite veritabanı bağlantısı
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Özel stil tanımlamaları
def create_styles():
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Title'],
        fontName='Arial',
        fontSize=24,
        spaceAfter=30,
        alignment=1
    ))
    
    styles.add(ParagraphStyle(
        name='CustomHeading',
        parent=styles['Heading1'],
        fontName='Arial',
        fontSize=16,
        spaceAfter=20
    ))
    
    styles.add(ParagraphStyle(
        name='CustomBody',
        parent=styles['Normal'],
        fontName='Arial',
        fontSize=11,
        spaceAfter=12
    ))
    
    return styles

# Veritabanı modeli
class UserResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False)
    question = db.Column(db.String(200), nullable=False)
    answer = db.Column(db.String(500), nullable=False)

# Veritabanını oluştur
with app.app_context():
    db.create_all()

# Sorular ve koşullu sorular - (Buraya önceki questions listesi gelecek)
questions = [
    {"question": "Adınız Soyadınız:", "type": "text"},
    {"question": "Yaşınız:", "type": "text"},
    {"question": "Cinsiyetiniz:", "type": "radio", "options": ["Kadın", "Erkek"]},
    # ... diğer sorularınız
]

# Route'lar
@app.route("/")
def home():
    if "session_id" not in session:
        session["session_id"] = os.urandom(16).hex()
    return render_template("corporate.html")

@app.route("/corporate")
def corporate():
    return render_template("corporate.html")

@app.route("/services")
def services():
    return render_template("services.html")

@app.route("/team")
def team():
    return render_template("team.html")

@app.route("/goals")
def goals():
    return render_template("goals.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/chat")
def chat():
    return render_template("index.html")

@app.route("/entry")
def entry():
    return render_template("entry.html")

# VERİ ANALİZİ ÖZELLİKLERİNİ DEVRE DIŞI BIRAK
@app.route("/data-analysis")
def data_analysis():
    return render_template("maintenance.html")  # Bakım sayfası göster

@app.route("/analyze", methods=["POST"])
def analyze():
    return jsonify({"error": "Veri analizi özelliği şu anda bakımda"}), 503

@app.route("/get_conversation", methods=["GET"])
def get_conversation():
    session_id = session.get("session_id")
    responses = UserResponse.query.filter_by(session_id=session_id).all()
    conversation = [{"question": resp.question, "answer": resp.answer} for resp in responses]
    return jsonify(conversation)

@app.route("/get_question", methods=["GET"])
def get_question():
    session_id = session.get("session_id")
    responses = UserResponse.query.filter_by(session_id=session_id).all()

    answered_questions = {resp.question for resp in responses}
    considered_questions = set()

    for question_data in questions:
        question_text = question_data["question"]

        if question_text in answered_questions or question_text in considered_questions:
            continue

        considered_questions.add(question_text)

        if "condition" in question_data:
            condition_met = True
            for cond_question, cond_values in question_data["condition"].items():
                user_answer = next((resp.answer for resp in responses if resp.question == cond_question), None)
                if user_answer not in cond_values:
                    condition_met = False
                    break
            if not condition_met:
                continue

        return jsonify({
            "question": question_text,
            "type": question_data["type"],
            "options": question_data.get("options"),
            "min": question_data.get("min"),
            "max": question_data.get("max")
        })

    return jsonify({"question": None})

@app.route("/submit_answer", methods=["POST"])
def submit_answer():
    data = request.json
    answer = data.get("answer", "").strip()
    question = data.get("question", "").strip()
    session_id = session.get("session_id")

    if session_id and question:
        already_answered = UserResponse.query.filter_by(session_id=session_id, question=question).first()
        if not already_answered:
            new_response = UserResponse(session_id=session_id, question=question, answer=answer)
            db.session.add(new_response)
            db.session.commit()
            return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Tüm sorular yanıtlandı veya bu soru zaten cevaplandı!"})

@app.route("/reset_chat", methods=["POST"])
def reset_chat():
    session_id = session.get("session_id")
    if session_id:
        UserResponse.query.filter_by(session_id=session_id).delete()
        db.session.commit()

    session["session_id"] = os.urandom(16).hex()
    return jsonify({"status": "success", "redirect": "/"})

@app.route("/download_pdf", methods=["GET"])
def download_pdf():
    session_id = session.get("session_id")
    responses = UserResponse.query.filter_by(session_id=session_id).all()

    if not responses:
        return jsonify({"status": "error", "message": "Sohbet boş!"})

    pdf_filename = os.path.join(basedir, "sohbet.pdf")
    doc = SimpleDocTemplate(pdf_filename, pagesize=letter)
    styles = getSampleStyleSheet()
    styles["BodyText"].fontName = "Arial"
    styles["Title"].fontName = "Arial"
    styles["Heading1"].fontName = "Arial"
    styles["Heading2"].fontName = "Arial"

    story = []

    # PDF içeriği - (önceki PDF oluşturma kodunuz)
    story.append(Spacer(1, 120))
    story.append(Paragraph("<para align='center'><font size=22><b>Anamnez Sohbet Raporu</b></font></para>", styles["Title"]))
    story.append(Spacer(1, 24))
    story.append(Paragraph(f"<para align='center'>Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}</para>", styles["BodyText"]))
    story.append(PageBreak())

    # Soru ve cevapları ekle
    for response in responses:
        story.append(Paragraph(f"<b>{response.question}</b>", styles["Heading2"]))
        story.append(Paragraph(response.answer, styles["BodyText"]))
        story.append(Spacer(1, 12))

    doc.build(story)
    
    @after_this_request
    def remove_file(response):
        try:
            os.remove(pdf_filename)
        except Exception as error:
            print("Dosya silinemedi:", error)
        return response
    
    return send_file(pdf_filename, as_attachment=True)

@app.route("/analysis", methods=["GET"])
def analysis():
    return render_template("maintenance.html")  # Bakım sayfası

@app.route('/upload', methods=['POST'])
def upload():
    try:
        if 'file' not in request.files:
            return jsonify({'message': 'Lütfen bir PDF dosyası yükleyin.'}), 400
        
        file = request.files['file']
        if not file.filename.endswith('.pdf'):
            return jsonify({'message': 'Lütfen sadece PDF dosyası yükleyin.'}), 400

        try:
            pdf_bytes = file.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            return jsonify({'message': 'PDF dosyası açılırken bir hata oluştu.'}), 400

        try:
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            
            if not text.strip():
                return jsonify({'message': 'PDF dosyası boş veya metin içermiyor.'}), 400
        except Exception as e:
            return jsonify({'message': 'PDF dosyasından metin çıkarılırken bir hata oluştu.'}), 400

    
        
# Kullanıcının sorusunu al
        user_query = request.form.get('query', '')
        if not user_query:
            user_query = """
1.⁠ ⁠Anamnez Soruları
•⁠  ⁠Açık uçlu anamnez sorularına verilen cevaplara yorum yapma.
•⁠  ⁠Katılımcının verdiği yanıtları yalnızca özetle.
•⁠  ⁠Kişisel ifadeleri değiştirme, çıkarımda bulunma, analiz etme.
•⁠  ⁠Bu bölümü sadece bilgi aktaran bir yapıda sun.

⸻

SCL 14 A ICIN PROMPT (Yani soru 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47 ve 48): Danışanın SCL-14 Anksiyete Ölçeği'ndeki 14 maddeye verdiği yanıtları aşağıdaki şekilde puanla:
Hiç: 0
Çok az: 1
Orta derecede: 2
Oldukça fazla: 3
Aşırı düzeyde: 4
Ardından şu adımları takip et:
Tüm maddelerin puanlarını topla.
Toplam puanı 14'e bölerek ortalama puanı hesapla.
Elde edilen ortalama puanı şu şekilde kategorilere ayır:
0.00 – 1.49 arası: Normal düzey
1.50 – 2.49 arası: Orta düzey
2.50 – 4.00 arası: Yüksek düzey

BECK ANKSIYETE ICIN PROMPT (Yani soru 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68 ve 69): Danışanın Beck Anksiyete Ölçeği'ndeki 21 maddeye verdiği yanıtları şu şekilde puanla:
Hiç: 0
Hafif Derecede: 1
Orta Derecede: 2
Ciddi Derecede: 3
Ardından şu adımları takip et:
Tüm maddelerin puanlarını toplayarak toplam puanı hesapla.
Toplam puanı aşağıdaki kategorilere göre değerlendir:
0–17 puan: Düşük düzeyde anksiyete
18–24 puan: Orta düzeyde anksiyete
25 ve üzeri puan: Yüksek düzeyde anksiyete

⸻

3.⁠ ⁠Demografik Bilgiler
•⁠  ⁠Katılımcının yaşı, cinsiyeti, medeni durumu, eğitim düzeyi gibi demografik verileri belirle.
•⁠  ⁠Bu bilgileri kısa ve betimleyici cümlelerle sun.
•⁠  ⁠Cümleler açık, akademik ve tarafsız bir dille yazılmalı.

⸻

Genel Kurallar
•⁠  ⁠Sadece PDF içeriğinde bulunan verileri kullan.
•⁠  ⁠Metinde olmayan hiçbir veriyi ekleme, yorumlama yapma.
•⁠  ⁠Varsayımda bulunma, dışsal bilgi katma.
•⁠  ⁠Cevapların tamamı Türkçe, akademik ve sistematik olmalı.
•⁠  ⁠Giriş, gelişme, sonuç yapısı içinde net ve düzenli analiz üret.
"""


        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"{user_query}:\n\n{text}"
            response = model.generate_content(prompt)
            
            if not response or not response.text:
                return jsonify({'message': 'AI modeli yanıt üretemedi.'}), 500
                
            return jsonify({'message': response.text})
        except Exception as e:
            print(f"Gemini API Hatası: {str(e)}")
            return jsonify({'message': 'Yapay zeka analizi sırasında bir hata oluştu.'}), 500

    except Exception as e:
        print(f"Genel Hata: {str(e)}")
        return jsonify({'message': 'Beklenmeyen bir hata oluştu.'}), 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5002))
    debug = not ('RENDER' in os.environ)
    
    print("Uygulama başlatılıyor...")
    print("API Anahtarı durumu:", "Ayarlanmış" if GEMINI_API_KEY else "Ayarlanmamış")
    print(f"Port: {port}")
    print(f"Debug Mode: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
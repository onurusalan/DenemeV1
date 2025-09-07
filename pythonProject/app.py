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
import matplotlib
matplotlib.use('Agg')  # GUI olmayan backend kullan
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from io import BytesIO
import os.path
import platform

# Ortam değişkenlerini yükle
load_dotenv()
GEMINI_API_KEY = "AIzaSyDBacTP1FYjR61hHBUNLCEtLAyk5vqFPiI"

app = Flask(__name__, template_folder="templates")

# Font yönetimi
def setup_fonts():
    try:
        # Mac OS için font yolları
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
                # Eğer Arial bulunamazsa, Times-Roman kullan
                print("Arial font bulunamadı, Times-Roman kullanılıyor...")
                pdfmetrics.registerFont(TTFont('Arial', 'Times-Roman'))
        else:
            # Diğer sistemler için
            font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'Arial.ttf')
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('Arial', font_path))
            else:
                print("Arial font bulunamadı, Times-Roman kullanılıyor...")
                pdfmetrics.registerFont(TTFont('Arial', 'Times-Roman'))
                
    except Exception as e:
        print(f"Font yükleme hatası: {str(e)}")
        print("Varsayılan font kullanılıyor...")
        # Varsayılan font kullanımı
        pdfmetrics.registerFont(TTFont('Arial', 'Times-Roman'))

# Font kurulumunu çağır
setup_fonts()

# Gemini API anahtarını ayarla
genai.configure(api_key=GEMINI_API_KEY)

# Static dosya (CSS, JS) sunumu için
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


app.secret_key = "supersecretkey"

# Güvenlik ayarları
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
    
    # Başlık stili
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Title'],
        fontName='Arial',
        fontSize=24,
        spaceAfter=30,
        alignment=1  # Ortalı
    ))
    
    # Alt başlık stili
    styles.add(ParagraphStyle(
        name='CustomHeading',
        parent=styles['Heading1'],
        fontName='Arial',
        fontSize=16,
        spaceAfter=20
    ))
    
    # Normal metin stili
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

# Sorular ve koşullu sorular
questions = [
    {"question": "Adınız Soyadınız:", "type": "text"},
    {"question": "Yaşınız:", "type": "text"},
    {"question": "Cinsiyetiniz:", "type": "radio", "options": ["Kadın", "Erkek"]},
    {"question": "Şu anda adet (menstrüasyon) döneminde misiniz?", "type": "radio", "options": ["Evet", "Hayır"],
     "condition": {"Cinsiyetiniz:": ["Kadın"]}},
    {"question": "Aşağıdaki seçeneklerden hangisi şu anki ilişki durumunuzu en iyi yansıtır?", "type": "radio", "options": [
        "Evli", "Bekar (hiç evlenmedi)", "Evli değilim, şu anda bir ilişkim var", "Şu anda bir ilişkim yok",
        "Nişanlı / sözlü", "Boşandım", "Diğer"
    ]},
    {"question": "Evliliğiniz/ilişkiniz ne kadar süredir devam ediyor? (Yıl ve ay belirtiniz)", "type": "text",
     "condition": {"Aşağıdaki seçeneklerden hangisi şu anki ilişki durumunuzu en iyi yansıtır?": ["Evli", "Evli değilim, şu anda bir ilişkim var", "Nişanlı / sözlü"]}},
    {"question": "Şu anda bir eğitim öğretim programına kayıtlı mısınız?", "type": "radio", "options": ["Evet", "Hayır"]},
    {"question": "Şu anda öğrenim gördüğünüz programın düzeyi nedir?", "type": "radio", "options": [
        "Lise", "Meslek Yüksekokulu", "Lisans (Üniversite)", "Yüksek Lisans", "Doktora", "Diğer"
    ], "condition": {"Şu anda bir eğitim öğretim programına kayıtlı mısınız?": ["Evet"]}},
    {"question": "Bölüm / Fakülte / Alan:", "type": "text",
     "condition": {"Şu anda bir eğitim öğretim programına kayıtlı mısınız?": ["Evet"]}},
    {"question": "En son tamamladığınız eğitim düzeyi nedir?", "type": "radio", "options": [
        "Lise", "Meslek Yüksekokulu", "Lisans (Üniversite)", "Yüksek Lisans", "Doktora", "Diğer"
    ], "condition": {"Şu anda bir eğitim öğretim programına kayıtlı mısınız?": ["Hayır"]}},
    {"question": "Bölüm / Fakülte / Alan:", "type": "text",
     "condition": {"Şu anda bir eğitim öğretim programına kayıtlı mısınız?": ["Hayır"]}},
    {"question": "Şu anda size maddi gelir sağlayan herhangi bir işte çalışıyor musunuz?", "type": "radio", "options": ["Evet", "Hayır"]},
    {"question": "Sigara veya tütün ürünü (nargile, elektronik sigara, puro vb.) kullanıyor musunuz?", "type": "radio", "options": ["Evet", "Hayır", "Bazen"]},
    {"question": "Ne sıklıkla sigara/tütün ürünü kullanıyorsunuz?", "type": "radio", "options": [
        "Her gün", "Haftada birkaç kez", "Haftada bir", "Ayda birkaç kez", "Ayda bir", "Yalnızca sosyal ortamlarda", "Çok nadiren (yılda birkaç kez)"
    ], "condition": {"Sigara veya tütün ürünü (nargile, elektronik sigara, puro vb.) kullanıyor musunuz?": ["Evet", "Bazen"]}},
    {"question": "Ne kadar sigara/tütün ürünü kullanıyorsunuz?", "type": "radio", "options": [
        "Günde birden fazla kez", "Günde 1 kez", "Haftada birkaç kez", "Ayda birkaç kez", "Yılda birkaç kez"
    ], "condition": {"Sigara veya tütün ürünü (nargile, elektronik sigara, puro vb.) kullanıyor musunuz?": ["Evet", "Bazen"]}},
    {"question": "Alkol kullanıyor musunuz?", "type": "radio", "options": ["Evet", "Hayır", "Bazen"]},
    {"question": "Ne sıklıkla alkol tüketirsiniz?", "type": "radio", "options": [
        "Her gün", "Haftada birkaç gün", "Haftada bir", "Ayda birkaç kez", "Ayda bir", "Yalnızca sosyal ortamlarda", "Çok nadiren (yılda 1-2 kez)"
    ], "condition": {"Alkol kullanıyor musunuz?": ["Evet"]}},
    {"question": "Ne kadar alkol tüketirsiniz?", "type": "radio", "options": [
        "Günde 2 veya daha fazla içki", "Günde 1 içki", "Haftada toplam 1-2 içki", "Ayda toplam 1-2 içki", "Her seferinde 1 içki", "Yılda 1-2 içki"
    ], "condition": {"Alkol kullanıyor musunuz?": ["Evet"]}},
    {"question": "Şu anda herhangi bir kronik rahatsızlığınız var mı? (Diyabet, hipertansiyon, astım, tiroid hastalıkları, ruhsal bozukluklar vb.)", "type": "radio", "options": ["Evet", "Hayır"]},
    {"question": "Kronik rahatsızlığınız varsa belirtiniz:", "type": "text",
     "condition": {"Şu anda herhangi bir kronik rahatsızlığınız var mı? (Diyabet, hipertansiyon, astım, tiroid hastalıkları, ruhsal bozukluklar vb.)": ["Evet"]}},
    {"question": "Düzenli olarak kullandığınız bir ilaç var mı?", "type": "radio", "options": ["Evet", "Hayır"]},
    {"question": "Düzenli olarak kullandığınız ilacın adını yazınız:", "type": "text",
     "condition": {"Düzenli olarak kullandığınız bir ilaç var mı?": ["Evet"]}},
    {"question": "Son 6 ay içerisinde antipsikotik veya antidepresan ilaç kullandınız mı?", "type": "radio", "options": ["Evet", "Hayır"]},
    {"question": "Geçmişte önemli bir sağlık sorunu yaşadınız mı? (Ameliyat, ciddi yaralanma, tanı almış hastalıklar vb.)", "type": "radio", "options": ["Evet", "Hayır"]},
    {"question": "Geçmişte yaşadığınız önemli sağlık sorununu belirtiniz:", "type": "text",
     "condition": {"Geçmişte önemli bir sağlık sorunu yaşadınız mı? (Ameliyat, ciddi yaralanma, tanı almış hastalıklar vb.)": ["Evet"]}},
    {"question": "Nörolojik bir rahatsızlığınız var mı? (Epilepsi, migren, MS vb.)", "type": "radio", "options": ["Evet", "Hayır"]},
    {"question": "Nörolojik rahatsızlığınız varsa belirtiniz:", "type": "text",
     "condition": {"Nörolojik bir rahatsızlığınız var mı? (Epilepsi, migren, MS vb.)": ["Evet"]}},
    {"question": "Birinci derece yakınlarınızda psikiyatrik rahatsızlığı olan biri var mı?", "type": "radio", "options": ["Evet", "Hayır"]},
    {"question": "Daha önce bir ruh sağlığı uzmanına (psikolog, psikiyatrist veya psikolojik danışman) başvurdunuz mu?", "type": "radio", "options": ["Evet", "Hayır", "Yanıtlamak istemiyorum"]},
    {"question": "Bu başvurunuz sonucunda herhangi bir psikolojik destek veya tedavi aldınız mı?", "type": "radio", "options": ["Evet", "Hayır", "Yanıtlamak istemiyorum"],
     "condition": {"Daha önce bir ruh sağlığı uzmanına (psikolog, psikiyatrist veya psikolojik danışman) başvurdunuz mu?": ["Evet"]}},
    {"question": "Bu başvurunuz toplam kaç seans/oturum sürdü?", "type": "text",
     "condition": {"Daha önce bir ruh sağlığı uzmanına (psikolog, psikiyatrist veya psikolojik danışman) başvurdunuz mu?": ["Evet"]}},
    {"question": "Son 6 ayda genel sağlık durumunuzu nasıl değerlendirirsiniz?", "type": "radio", "options": [
        "Çok iyi", "Çoğunlukla sağlıklı hissettim", "Ne kötü ne iyi", "Kötü", "Çok kötü"
    ]},
    {"question": "Son 6 ayda, genel olarak günleriniz nasıl geçti?", "type": "radio", "options": [
        "Çok iyi", "İyi", "Ne iyi ne kötü", "Kötü", "Çok kötü"
    ]},
    {"question": "Son 6 ay içinde aşağıdaki fiziksel belirtilerden hangilerini yaşadınız? (Yaşadığınız belirtileri seçiniz)", "type": "checkbox", "options": [
        "Uyku düzensizliği", "Kâbus görme", "Baş dönmesi", "Mide bulantısı", "Kalp çarpıntısı", "Tansiyon problemi", "Nefes darlığı", "Yeme düzeninde değişiklik",
        "Aşırı terleme", "Kas gerginliği", "Uyuşma veya karıncalanma hissi"
    ]},




    # --- BÖLÜM 4: SCL A14 ANKETİ (DÜZELTİLMİŞ) ---
{
    "question": "SCL A14 - Yönerge: Lütfen son 6 ay içerisinde aşağıda yer alan durumları ne sıklıkta yaşadığınızı değerlendirin.",
    "type": "radio",
    "options": ["Devam"]
},
{
    "question": "Her şey için çok fazla endişe duyma",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Sinirlilik ya da içinin titremesi",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Sizi korkutan belirli uğraş, yer veya nesnelerden kaçınma durumu",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Uykuda huzursuzluk, rahat uyuyamama",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Düşüncelerinizi bir konuya yoğunlaştırmada güçlük",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Gelecek konusunda ümitsizlik",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Adele (kas) ağrıları",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Soğuk veya sıcak basması",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Kalbin çok hızlı çarpması",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Nefes almada güçlük",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Bulantı ve midede rahatsızlık hissi",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Cinsel arzu ve ilginin kaybı",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Baygınlık ya da baş dönmesi",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},
{
    "question": "Enerjinizde azalma veya yavaşlama hali",
    "type": "radio",
    "options": ["Hiç", "Çok Az", "Orta Derecede", "Oldukça Fazla", "İleri Derecede"]
},

# --- BÖLÜM 5: BECK ANKSİYETE ÖLÇEĞİ (DÜZELTİLMİŞ) ---
{
    "question": "BECK ANKSİYETE - Yönerge: Lütfen her bir durumu son 6 ay içinde ne kadar yoğun yaşadığınızı düşünerek işaretleyiniz.",
    "type": "radio",
    "options": ["Devam"]
},
{
    "question": "Bedeninizin herhangi bir yerinde uyuşma veya karıncalanma",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Sıcak/ ateş basmaları",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Bacaklarda halsizlik, titreme",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Gevşeyememe",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Çok kötü şeyler olacak korkusu",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Baş dönmesi veya sersemlik",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Kalp çarpıntısı",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Dengeyi kaybetme duygusu",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Dehşete kapılma",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Sinirlilik",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Boğuluyormuş gibi olma duygusu",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Ellerde titreme",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Titreklik",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Kontrolü kaybetme korkusu",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Nefes almada güçlük",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Ölüm korkusu",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Korkuya kapılma",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Midede hazımsızlık ya da rahatsızlık hissi",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Baygınlık",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Yüzün kızarması",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},
{
    "question": "Terleme (sıcaklığa bağlı olmayan)",
    "type": "radio",
    "options": ["Hiç / Hafif düzeyde", "Beni pek etkilemedi", "Orta düzeyde", "Hoş değildi ama katlanabildim", "Ciddi düzeyde", "Dayanmakta çok zorlandım"]
},

    {
        "question": "Şu anda profesyonel yardım almak istemenize neden olan durum nedir? Lütfen yaşadığınız temel problemi kısaca açıklayınız.",
        "type": "text"
    },
    {
        "question": "Şu anda profesyonel yardım almak istemenize neden olan bu durum ne kadar süredir devam ediyor?",
        "type": "radio",
        "options": ["1 aydan az", "1-3 ay", "4-6 ay", "7-12 ay", "12 ay ve fazla"]
    },
    {
        "question": "Peki sizi tam da şu anda yardım almaya yönelten özel bir olay, değişim ya da tetikleyici bir durum oldu mu? Varsa belirtiniz.",
        "type": "text"
    },
    {
        "question": "Bu durum günlük yaşamınızı/işlevselliğinizi ne düzeyde etkiliyor?",
        "type": "radio",
        "options": [
            "Çok fazla etkiliyor – Günlük işlevlerimi ciddi şekilde aksatıyor",
            "Genellikle etkiliyor – Çoğu günlerde işlerimi zorlaştırıyor",
            "Bazen etkiliyor – Ara sıra günlük işlerimi etkiliyor",
            "Nadiren etkiliyor – Genelde hayatımı sürdürmemi engellemiyor",
            "Hiç etkilemiyor – Günlük yaşamımı etkilemiyor"
        ]
    },
    {
        "question": "Daha önce bu durumla başa çıkmak için hangi yolları denediniz? Lütfen size uygun olan tüm seçenekleri işaretleyiniz.",
        "type": "checkbox",
        "options": [
            "Profesyonel yardım aldım (psikolog, psikiyatrist, danışman vb.)",
            "Ailemin veya yakın çevremin desteğini aldım",
            "İlaç desteği aldım",
            "Hastanede yatışım oldu",
            "Herhangi bir destek almadım / kendi başıma başa çıkmaya çalıştım",
            "Başka yöntemler denedim" # Ayrı bir text sorusu ile detay alınabilir
        ]
    },
    {
        "question": "Bu durumla başa çıkma sürecinizde yaptıklarınızın ne düzeyde etkili olduğunu düşünüyorsunuz?",
        "type": "radio",
        "options": ["Çok etkili", "Oldukça etkili", "Ne etkili ne etkisiz", "Az etkili", "Hiç etkili değil"]
    }
]

# Duplicate soru kontrolü ve temizleme işlemi
question_texts = [q["question"] for q in questions]
unique_questions = []
seen_questions = set()

for q in questions:
    if q["question"] not in seen_questions:
        seen_questions.add(q["question"])
        unique_questions.append(q)

questions = unique_questions  # Tekrarları kaldırılmış yeni liste

print(f"Güncellenmiş soru listesi: {len(questions)} soru var.")

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

@app.route("/data-analysis")
def data_analysis():
    return render_template("upload.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    if "file" not in request.files:
        return jsonify({"error": "Dosya yüklenmedi"}), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Dosya seçilmedi"}), 400
    
    # 1. Dosya Format Kontrolü
    if not file.filename.endswith(".csv"):
        return jsonify({"error": "Lütfen sadece CSV dosyası yükleyin"}), 400
    
    # Dosya boyutu kontrolü (5MB)
    file_content = file.read()
    if len(file_content) > 5 * 1024 * 1024:  # 5MB in bytes
        return jsonify({"error": "Dosya boyutu 5MB'dan büyük olamaz"}), 400
    
    try:
        # CSV dosyasını pandas ile oku
        df = pd.read_csv(BytesIO(file_content))
        
        # Boş dosya kontrolü
        if len(df) == 0:
            return jsonify({"error": "CSV dosyası boş"}), 400
            
        # Sayısal veri kontrolü
        numeric_columns = df.select_dtypes(include=[np.number]).columns
        if len(numeric_columns) == 0:
            return jsonify({"error": "CSV dosyası sayısal veri içermiyor"}), 400
        
        # Temel istatistikler
        basic_stats = [
            {"name": "Toplam Veri", "value": len(df)},
            {"name": "Sütun Sayısı", "value": len(df.columns)},
            {"name": "Eksik Veri", "value": df.isnull().sum().sum()}
        ]
        
        # Detaylı istatistikler
        describe = df.describe()
        detailed_stats = []
        for col in describe.columns:
            for stat in describe.index:
                detailed_stats.append({
                    "name": f"{col} - {stat}",
                    "value": f"{describe[col][stat]:.2f}"
                })
        
        # Grafikleri oluştur
        graph_files = []
        
        # 1. Histogramlar
        for col in numeric_columns:
            plt.figure(figsize=(10, 6))
            plt.hist(df[col].dropna(), bins=30, alpha=0.7)
            plt.title(f"{col} Dağılımı")
            plt.xlabel(col)
            plt.ylabel("Frekans")
            filename = f"pythonProject/static/graphs/histogram_{col}.png"
            plt.savefig(filename, bbox_inches="tight", dpi=300)
            plt.close()
            graph_files.append(f"graphs/histogram_{col}.png")
        
        # 2. Boxplot
        plt.figure(figsize=(12, 6))
        df[numeric_columns].boxplot()
        plt.title("Değişkenlerin Dağılımı (Boxplot)")
        plt.xticks(rotation=45)
        filename = "pythonProject/static/graphs/boxplot.png"
        plt.savefig(filename, bbox_inches="tight", dpi=300)
        plt.close()
        graph_files.append("graphs/boxplot.png")
        
        # 3. Violin Plot
        plt.figure(figsize=(12, 6))
        for i, col in enumerate(numeric_columns, 1):
            plt.subplot(1, len(numeric_columns), i)
            sns.violinplot(y=df[col])
            plt.title(f"{col}")
        plt.tight_layout()
        filename = "pythonProject/static/graphs/violin.png"
        plt.savefig(filename, bbox_inches="tight", dpi=300)
        plt.close()
        graph_files.append("graphs/violin.png")
        
        # 4. Korelasyon Heatmap
        if len(numeric_columns) > 1:
            plt.figure(figsize=(10, 8))
            sns.heatmap(df[numeric_columns].corr(), annot=True, cmap='coolwarm', center=0)
            plt.title("Değişkenler Arası Korelasyon")
            filename = "pythonProject/static/graphs/correlation.png"
            plt.savefig(filename, bbox_inches="tight", dpi=300)
            plt.close()
            graph_files.append("graphs/correlation.png")
        
        # 5. Zaman Serisi Analizi
        time_series = False
        if 'ID' in df.columns and any(col.lower().startswith(('tarih', 'date', 'time')) for col in df.columns):
            time_cols = [col for col in df.columns if col.lower().startswith(('tarih', 'date', 'time'))]
            if time_cols:
                time_col = time_cols[0]
                df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
                
                for col in numeric_columns:
                    if col != 'ID':
                        plt.figure(figsize=(12, 6))
                        for id_val in df['ID'].unique():
                            temp_df = df[df['ID'] == id_val]
                            plt.plot(temp_df[time_col], temp_df[col], marker='o', label=f'ID: {id_val}')
                        plt.title(f"{col} Değerinin Zaman İçindeki Değişimi")
                        plt.xlabel("Tarih")
                        plt.ylabel(col)
                        plt.legend()
                        plt.xticks(rotation=45)
                        filename = f"pythonProject/static/graphs/timeseries_{col}.png"
                        plt.savefig(filename, bbox_inches="tight", dpi=300)
                        plt.close()
                        graph_files.append(f"graphs/timeseries_{col}.png")
                time_series = True
        
        # PDF Raporu Oluştur
        pdf_filename = os.path.join("pythonProject/static/reports", "analysis_report.pdf")
        doc = SimpleDocTemplate(pdf_filename, pagesize=letter)
        story = []
        
        # Başlık
        styles = getSampleStyleSheet()
        # Başlık stili
        styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=styles['Title'],
            fontName='Arial',
            fontSize=24,
            alignment=1,  # Ortalı
            spaceAfter=30
        ))
        
        # Normal metin stili
        styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=styles['Normal'],
            fontName='Arial',
            fontSize=12,
            leading=16
        ))
        
        # Başlık 1 stili
        styles.add(ParagraphStyle(
            name='CustomHeading1',
            parent=styles['Heading1'],
            fontName='Arial',
            fontSize=16,
            spaceAfter=16
        ))

        story.append(Paragraph("Veri Analizi Raporu", styles['CustomTitle']))
        story.append(Spacer(1, 20))
        
        # Dosya Bilgileri
        story.append(Paragraph(f"Dosya Adı: {file.filename}", styles['CustomNormal']))
        story.append(Paragraph(f"Analiz Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['CustomNormal']))
        story.append(Spacer(1, 20))
        
        # Temel İstatistikler
        story.append(Paragraph("Temel İstatistikler", styles['CustomHeading1']))
        data = [[Paragraph("Metrik", styles['CustomNormal']), 
                Paragraph("Değer", styles['CustomNormal'])]]
        
        for stat in basic_stats:
            data.append([
                Paragraph(stat["name"], styles['CustomNormal']),
                Paragraph(str(stat["value"]), styles['CustomNormal'])
            ])
        
        t = Table(data, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Arial'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(t)
        story.append(Spacer(1, 20))
        
        # Grafikler
        story.append(Paragraph("Görsel Analizler", styles['CustomHeading1']))
        for graph_file in graph_files:
            img_path = os.path.join("pythonProject/static", graph_file)
            img = Image(img_path, width=450, height=300)
            story.append(img)
            story.append(Spacer(1, 20))
        
        # PDF'i oluştur
        doc.build(story)
        
        return render_template("analysis_result.html",
                             filename=file.filename,
                             basic_stats=basic_stats,
                             detailed_stats=detailed_stats,
                             graphs=graph_files,
                             time_series=time_series)
                             
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont('Arial', 9)
    page_num = canvas.getPageNumber()
    text = f"Sayfa {page_num}"
    canvas.drawRightString(letter[0]-30, 30, text)
    canvas.drawString(30, 30, "© AnamnesisGPT • Veri Analizi Raporu")
    canvas.restoreState()

def get_graph_title(graph_file):
    """Grafik dosya adından başlık oluştur"""
    if 'histogram' in graph_file:
        return "Histogram Analizi"
    elif 'boxplot' in graph_file:
        return "Kutu Grafiği Analizi"
    elif 'violin' in graph_file:
        return "Violin Plot Analizi"
    elif 'correlation' in graph_file:
        return "Korelasyon Analizi"
    elif 'timeseries' in graph_file:
        return "Zaman Serisi Analizi"
    return "Grafik Analizi"

def get_graph_description(graph_file, df):
    """Grafik için otomatik yorum oluştur"""
    if 'histogram' in graph_file:
        col_name = graph_file.split('_')[1].split('.')[0]
        mean = df[col_name].mean()
        std = df[col_name].std()
        skew = df[col_name].skew()
        
        description = f"{col_name} değişkeni için ortalama {mean:.2f}, standart sapma {std:.2f}. "
        if skew > 0.5:
            description += "Dağılım sağa çarpık."
        elif skew < -0.5:
            description += "Dağılım sola çarpık."
        else:
            description += "Dağılım normale yakın."
            
        return description
        
    elif 'correlation' in graph_file:
        corr_matrix = df.corr()
        high_corr = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i):
                if abs(corr_matrix.iloc[i, j]) > 0.6:
                    high_corr.append(f"{corr_matrix.columns[i]} ve {corr_matrix.columns[j]} arasında güçlü bir ilişki (r={corr_matrix.iloc[i, j]:.2f})")
        
        if high_corr:
            return "Önemli korelasyonlar: " + "; ".join(high_corr)
        return "Değişkenler arasında güçlü bir ilişki gözlenmemiştir."
        
    return "Bu grafik veri dağılımını ve ilişkilerini göstermektedir."

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

    # Kullanıcının zaten yanıtladığı soruları bir sete ekleyelim
    answered_questions = {resp.question for resp in responses}

    # 🔹 Aynı sorunun iki kez gönderilmemesi için bu seti kullanacağız
    considered_questions = set()

    for question_data in questions:
        question_text = question_data["question"]

        # Eğer soru zaten sorulmuş veya işlendi ise atla
        if question_text in answered_questions or question_text in considered_questions:
            continue

        considered_questions.add(question_text)  # Eklenenleri takip et

        # 🔹 Koşullu sorular varsa ve kullanıcı uygun değilse atla
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

    return jsonify({"question": None})  # Eğer sorular bittiyse None döndür

@app.route("/submit_answer", methods=["POST"])
def submit_answer():
    data = request.json
    answer = data.get("answer", "").strip()
    question = data.get("question", "").strip()
    session_id = session.get("session_id")

    if session_id and question:
        # Sadece o soruya cevap kaydet
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

    # Oturumu temizlemek yerine yeni bir oturum ID'si atama
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

    # Kapak sayfası
    story.append(Spacer(1, 120))
    story.append(Paragraph("<para align='center'><font size=22><b>Anamnez Sohbet Raporu</b></font></para>", styles["Title"]))
    story.append(Spacer(1, 24))
    story.append(Paragraph("<para align='center'><font size=12>Gizli/Özel</font></para>", styles["BodyText"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("<para align='center'>Bu rapor, danışan ile yapılan psikolojik anamnez görüşmesinin otomatik çıktısıdır.</para>", styles["BodyText"]))
    story.append(Spacer(1, 24))
    story.append(Paragraph(f"<para align='center'>Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}</para>", styles["BodyText"]))
    story.append(PageBreak())

    # Soru ve cevapları gruplandır
    dsm_cevaplari = []
    fiziksel_cevaplar = []
    genel_cevaplar = []

    for response in responses:
        if response.question == "DSM Soruları (Evet/Hayır):":
            dsm_cevaplari = response.answer.split(", ")
        elif response.question == "Fiziksel/Somatik Şikayetleriniz:":
            fiziksel_cevaplar = response.answer.split(", ")
        else:
            genel_cevaplar.append((response.question, response.answer))

    # Kişisel Bilgiler (Tablo)
    story.append(Paragraph("<b>Kişisel Bilgiler</b>", styles["Heading1"]))
    data = []
    for q, a in genel_cevaplar[:6]:
        data.append([Paragraph(f"<b>{q}</b>", styles["BodyText"]), Paragraph(a, styles["BodyText"])])
    table = Table(data, colWidths=[200, 300])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('BOX', (0, 0), (-1, -1), 1, colors.grey),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (-1, -1), 'Arial'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    story.append(table)
    story.append(Spacer(1, 18))

    # Klinik Geçmiş ve Problem Odaklı Sorular (Kartlar)
    story.append(Paragraph("<b>Klinik Geçmiş ve Problemler</b>", styles["Heading1"]))
    for q, a in genel_cevaplar[6:]:
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>{q}</b>", styles["Heading2"]))
        story.append(Paragraph(f"<font color='#444'>{a}</font>", styles["BodyText"]))
        story.append(Spacer(1, 8))

    # Fiziksel/Somatik Şikayetler (Madde madde, kutucuklu)
    if fiziksel_cevaplar:
        story.append(PageBreak())
        story.append(Paragraph("<b>Fiziksel/Somatik Şikayetler</b>", styles["Heading1"]))
        for item in fiziksel_cevaplar:
            story.append(Paragraph(f"&#9632; {item}", styles["BodyText"]))  # Kare kutucuk
        story.append(Spacer(1, 12))

    # DSM Soruları (Madde madde, kutucuklu)
    if dsm_cevaplari:
        story.append(PageBreak())
        story.append(Paragraph("<b>DSM Tanı Ölçütleri</b>", styles["Heading1"]))
        for item in dsm_cevaplari:
            story.append(Paragraph(f"&#9632; {item}", styles["BodyText"]))
        story.append(Spacer(1, 12))

    # Son
    story.append(PageBreak())
    story.append(Spacer(1, 60))
    story.append(Paragraph("Rapor, Anamnez GPT tarafından otomatik olarak oluşturulmuştur.", styles["BodyText"]))
    story.append(Spacer(1, 24))
    story.append(Paragraph(f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles["BodyText"]))
    story.append(Spacer(1, 36))
    story.append(Paragraph("Danışan İmzası: __________________________", styles["BodyText"]))

    doc.build(story)
    @after_this_request
    def remove_file(response):
        try:
            os.remove(pdf_filename)
        except Exception as error:
            print("Dosya silinemedi:", error)
        return response
    return send_file(pdf_filename, as_attachment=True)


# ANALYSIS.HTML İÇİN EKLENEN KISIMLAR
@app.route("/analysis", methods=["GET"])
def analysis():
    try:
        return render_template("analysis.html")
    except Exception as e:
        return f"Hata: {str(e)}"




# PDF'den metin çıkarma fonksiyonu ve Gemini ile analiz eden endpoint
@app.route('/upload', methods=['POST'])
def upload():
    try:
        if 'file' not in request.files:
            return jsonify({'message': 'Lütfen bir PDF dosyası yükleyin.'}), 400
        
        file = request.files['file']
        if not file.filename.endswith('.pdf'):
            return jsonify({'message': 'Lütfen sadece PDF dosyası yükleyin.'}), 400

        # PDF dosyasını oku
        try:
            pdf_bytes = file.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            return jsonify({'message': 'PDF dosyası açılırken bir hata oluştu. Lütfen dosyanın bozuk olmadığından emin olun.'}), 400

        # PDF'den metin çıkar
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
1. Anamnez Soruları
• Açık uçlu anamnez sorularına verilen cevaplara yorum yapma.
• Katılımcının verdiği yanıtları yalnızca özetle.
• Kişisel ifadeleri değiştirme, çıkarımda bulunma, analiz etme.
• Bu bölümü sadece bilgi aktaran bir yapıda sun.

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

3. Demografik Bilgiler
• Katılımcının yaşı, cinsiyeti, medeni durumu, eğitim düzeyi gibi demografik verileri belirle.
• Bu bilgileri kısa ve betimleyici cümlelerle sun.
• Cümleler açık, akademik ve tarafsız bir dille yazılmalı.

⸻

Genel Kurallar
• Sadece PDF içeriğinde bulunan verileri kullan.
• Metinde olmayan hiçbir veriyi ekleme, yorumlama yapma.
• Varsayımda bulunma, dışsal bilgi katma.
• Cevapların tamamı Türkçe, akademik ve sistematik olmalı.
• Giriş, gelişme, sonuç yapısı içinde net ve düzenli analiz üret.
"""

        # Gemini ile analiz et
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"{user_query}:\n\n{text}"
            response = model.generate_content(prompt)
            
            if not response or not response.text:
                return jsonify({'message': 'AI modeli yanıt üretemedi. Lütfen tekrar deneyin.'}), 500
                
            return jsonify({'message': response.text})
        except Exception as e:
            print(f"Gemini API Hatası: {str(e)}")  # Loglama için
            return jsonify({'message': 'Yapay zeka analizi sırasında bir hata oluştu. Lütfen daha sonra tekrar deneyin.'}), 500

    except Exception as e:
        print(f"Genel Hata: {str(e)}")  # Loglama için
        return jsonify({'message': 'Beklenmeyen bir hata oluştu. Lütfen daha sonra tekrar deneyin.'}), 500

if __name__ == "__main__":
    print("Uygulama başlatılıyor...")
    print("API Anahtarı durumu:", "Ayarlanmış" if GEMINI_API_KEY else "Ayarlanmamış")
    print("Uygulama http://localhost:5002 adresinde çalışıyor")
    app.run(debug=True, port=5002)

# Yeni eklenen kod bloğu
genai.configure(api_key="YOUR_API_KEY")
for m in genai.list_models():
    print(m.name)
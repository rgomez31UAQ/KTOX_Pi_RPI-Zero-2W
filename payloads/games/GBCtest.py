@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' in request.files:
            f = request.files['file']
            if f and f.filename:
                try:
                    save_path = os.path.join(ROM_DIR, f.filename)
                    f.save(save_path)
                    return redirect('/')
                except Exception as e:
                    return f"<h1>Upload failed: {str(e)}</h1>"
    try:
        roms = sorted(os.listdir(ROM_DIR))
    except:
        roms = []
    return render_template_string('''
        <body style="background:#000; color:#0f0; font-family:monospace; text-align:center; padding:20px;">
            <h1 style="color:red;">KTOx // GBC_INJECTOR</h1>
            <form method="post" enctype="multipart/form-data">
                <input type="file" name="file" style="background:#111; color:#0f0; border:1px solid #0f0; padding:8px;">
                <button type="submit" style="background:#f00; color:white; border:none; padding:10px 20px; margin-left:10px;">INJECT ROM</button>
            </form>
            <hr style="border-color:#333;">
            <h3>ROM VAULT ({{ len(roms) }} files)</h3>
            <ul style="list-style:none; padding:0; text-align:left; max-width:400px; margin:0 auto;">
                {% for r in roms %}<li style="margin:4px 0;">{{ r }}</li>{% endfor %}
            </ul>
            <p style="margin-top:30px; color:#666;">Upload .gb or .gbc files • Access at PI_IP:5000</p>
        </body>
    ''', roms=roms)

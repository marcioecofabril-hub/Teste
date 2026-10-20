import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import requests
from flask import Flask, jsonify, render_template, request, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="pix-link-v1")
MP_API = "https://api.mercadopago.com"


def mp_token():
    token = os.environ.get("MP_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("MP_ACCESS_TOKEN nao configurado")
    return token


def base_url():
    return os.environ.get("PUBLIC_BASE_URL", request.url_root.rstrip("/")).rstrip("/")


def money(value):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError("Valor invalido")
    if amount <= 0 or amount > Decimal("10000"):
        raise ValueError("O valor deve estar entre R$ 0,01 e R$ 10.000,00")
    return amount


def decode_link(token):
    return serializer.loads(token, max_age=60 * 60 * 24 * 30)


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        return render_template("pay_simple.html")

    name = (request.form.get("name") or "").strip()[:80]
    email = (request.form.get("email") or "").strip().lower()
    if not name:
        return render_template("pay_simple.html", error="Informe seu nome."), 400
    if "@" not in email:
        return render_template("pay_simple.html", error="Informe um e-mail valido."), 400

    payload = {
        "transaction_amount": 10.00,
        "description": "Pagamento de servico de TI",
        "payment_method_id": "pix",
        "external_reference": f"TI-{uuid.uuid4().hex[:12]}",
        "payer": {"email": email, "first_name": name},
    }
    headers = {
        "Authorization": f"Bearer {mp_token()}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4()),
    }
    try:
        response = requests.post(f"{MP_API}/v1/payments", json=payload, headers=headers, timeout=20)
        data = response.json()
    except requests.RequestException:
        return render_template("pay_simple.html", error="Falha de comunicacao com o Mercado Pago."), 502
    if response.status_code not in (200, 201):
        detail = data.get("message") or data.get("cause") or "Pagamento nao criado"
        return render_template("pay_simple.html", error=f"Mercado Pago: {detail}"), 400

    tx = (data.get("point_of_interaction") or {}).get("transaction_data") or {}
    qr_code, qr_base64 = tx.get("qr_code"), tx.get("qr_code_base64")
    payment_id = str(data.get("id"))
    status_token = serializer.dumps({"payment_id": payment_id})
    if not qr_code or not qr_base64:
        return render_template("message.html", title="QR Code indisponivel", message="O Mercado Pago nao retornou o QR Code."), 502
    return render_template("pix.html", charge={"amount":"10,00"}, qr_code=qr_code, qr_base64=qr_base64, payment_id=payment_id, status_token=status_token)


@app.get("/api/status/<status_token>")
def payment_status(status_token):
    try:
        payment_id = serializer.loads(status_token, max_age=60 * 60 * 24)["payment_id"]
    except (BadSignature, SignatureExpired, KeyError):
        return jsonify({"error": "token invalido"}), 400
    try:
        response = requests.get(f"{MP_API}/v1/payments/{payment_id}", headers={"Authorization": f"Bearer {mp_token()}"}, timeout=15)
        data = response.json()
    except requests.RequestException:
        return jsonify({"error": "falha de comunicacao"}), 502
    return jsonify({"status": data.get("status"), "status_detail": data.get("status_detail")}), response.status_code


@app.get("/health")
def health():
    return jsonify({"ok": True, "time": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)

import os
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, render_template, request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "dev-only-change-me"
)

serializer = URLSafeTimedSerializer(
    app.config["SECRET_KEY"],
    salt="pix-payment-v1"
)

MP_API = "https://api.mercadopago.com"


def mp_token():
    token = os.environ.get("MP_ACCESS_TOKEN", "").strip()

    if not token:
        raise RuntimeError("MP_ACCESS_TOKEN nao configurado")

    return token


@app.route("/", methods=["GET", "POST"])
def home():

    if request.method == "GET":
        return render_template("pay_simple.html")

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()

    if not name:
        return render_template(
            "pay_simple.html",
            error="Informe seu nome."
        ), 400

    if "@" not in email:
        return render_template(
            "pay_simple.html",
            error="Informe um e-mail valido."
        ), 400

    payload = {
        "transaction_amount": 10.00,
        "description": "Pagamento de servico de TI",
        "payment_method_id": "pix",
        "external_reference": f"TI-{uuid.uuid4().hex[:12]}",
        "payer": {
            "email": email,
            "first_name": name
        }
    }

    headers = {
        "Authorization": f"Bearer {mp_token()}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4())
    }

    try:
        response = requests.post(
            f"{MP_API}/v1/payments",
            json=payload,
            headers=headers,
            timeout=20
        )

        data = response.json()

    except requests.RequestException:
        return render_template(
            "pay_simple.html",
            error="Falha de comunicacao com o Mercado Pago."
        ), 502

    except ValueError:
        return render_template(
            "pay_simple.html",
            error="O Mercado Pago retornou uma resposta invalida."
        ), 502

    if response.status_code not in (200, 201):

        detail = data.get("message", "Pagamento nao criado")

        return render_template(
            "pay_simple.html",
            error=f"Mercado Pago: {detail}"
        ), 400

    point_of_interaction = data.get("point_of_interaction") or {}

    transaction_data = (
        point_of_interaction.get("transaction_data") or {}
    )

    qr_code = transaction_data.get("qr_code")
    qr_base64 = transaction_data.get("qr_code_base64")

    payment_id = str(data.get("id"))

    if not qr_code or not qr_base64:
        return render_template(
            "message.html",
            title="QR Code indisponivel",
            message="O Mercado Pago nao retornou o QR Code."
        ), 502

    status_token = serializer.dumps({
        "payment_id": payment_id
    })

    return render_template(
        "pix.html",
        amount="10,00",
        qr_code=qr_code,
        qr_base64=qr_base64,
        payment_id=payment_id,
        status_token=status_token
    )


@app.get("/api/status/<status_token>")
def payment_status(status_token):

    try:
        payload = serializer.loads(
            status_token,
            max_age=60 * 60 * 24
        )

        payment_id = payload["payment_id"]

    except (BadSignature, SignatureExpired, KeyError):
        return jsonify({
            "error": "token invalido"
        }), 400

    headers = {
        "Authorization": f"Bearer {mp_token()}"
    }

    try:
        response = requests.get(
            f"{MP_API}/v1/payments/{payment_id}",
            headers=headers,
            timeout=15
        )

        data = response.json()

    except requests.RequestException:
        return jsonify({
            "error": "falha de comunicacao"
        }), 502

    return jsonify({
        "status": data.get("status"),
        "status_detail": data.get("status_detail")
    }), response.status_code


@app.get("/health")
def health():

    return jsonify({
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat()
    })


if __name__ == "__main__":

    port = int(os.environ.get("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )

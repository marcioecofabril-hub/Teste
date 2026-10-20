import os
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

MP_API = "https://api.mercadopago.com"


def mp_token():
    token = os.environ.get("MP_ACCESS_TOKEN", "").strip()

    if not token:
        raise RuntimeError("MP_ACCESS_TOKEN nao configurado")

    return token


def mercado_pago_headers():
    return {
        "Authorization": f"Bearer {mp_token()}",
        "Content-Type": "application/json"
    }


@app.route("/", methods=["GET", "POST"])
def home():

    if request.method == "GET":
        return render_template("pay_simple.html")

    name = (request.form.get("name") or "").strip()[:80]
    email = (request.form.get("email") or "").strip().lower()

    if not name:
        return render_template(
            "pay_simple.html",
            error="Informe seu nome."
        ), 400

    if "@" not in email:
        return render_template(
            "pay_simple.html",
            error="Informe um e-mail válido."
        ), 400

    payload = {
        "transaction_amount": 10.00,
        "description": "Pagamento de serviço de TI",
        "payment_method_id": "pix",
        "external_reference": f"MDS-TI-{uuid.uuid4().hex[:12]}",
        "payer": {
            "email": email,
            "first_name": name
        }
    }

    headers = mercado_pago_headers()

    headers["X-Idempotency-Key"] = str(uuid.uuid4())

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
            error="Não foi possível comunicar com o Mercado Pago."
        ), 502

    except ValueError:
        return render_template(
            "pay_simple.html",
            error="O Mercado Pago retornou uma resposta inválida."
        ), 502

    if response.status_code not in (200, 201):

        detail = data.get("message", "Pagamento não criado")

        return render_template(
            "pay_simple.html",
            error=f"Mercado Pago: {detail}"
        ), 400

    transaction_data = (
        (data.get("point_of_interaction") or {})
        .get("transaction_data") or {}
    )

    qr_code = transaction_data.get("qr_code")
    qr_base64 = transaction_data.get("qr_code_base64")
    payment_id = str(data.get("id") or "")

    if not payment_id:
        return render_template(
            "message.html",
            title="Pagamento não identificado",
            message="O Mercado Pago não retornou o ID do pagamento."
        ), 502

    if not qr_code or not qr_base64:
        return render_template(
            "message.html",
            title="QR Code indisponível",
            message="O Mercado Pago não retornou o QR Code."
        ), 502

    return render_template(
        "pix.html",
        amount="10,00",
        qr_code=qr_code,
        qr_base64=qr_base64,
        payment_id=payment_id
    )


@app.get("/api/status/<payment_id>")
def payment_status(payment_id):

    if not payment_id.isdigit():
        return jsonify({
            "ok": False,
            "error": "ID de pagamento inválido"
        }), 400

    try:
        response = requests.get(
            f"{MP_API}/v1/payments/{payment_id}",
            headers=mercado_pago_headers(),
            timeout=15
        )

        data = response.json()

    except requests.RequestException:
        return jsonify({
            "ok": False,
            "error": "Falha de comunicação com o Mercado Pago"
        }), 502

    except ValueError:
        return jsonify({
            "ok": False,
            "error": "Resposta inválida do Mercado Pago"
        }), 502

    if response.status_code != 200:
        return jsonify({
            "ok": False,
            "error": data.get(
                "message",
                "Não foi possível consultar o pagamento"
            )
        }), response.status_code

    transaction_details = data.get("transaction_details") or {}

    return jsonify({
        "ok": True,
        "payment_id": str(data.get("id")),
        "status": data.get("status"),
        "status_detail": data.get("status_detail"),
        "transaction_amount": data.get("transaction_amount"),
        "net_received_amount": transaction_details.get(
            "net_received_amount"
        ),
        "date_approved": data.get("date_approved")
    }), 200


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

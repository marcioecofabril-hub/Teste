import os
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

MP_API = "https://api.mercadopago.com"


# ============================================================
# PLANOS DISPONIVEIS
# O valor e definido somente no servidor.
# ============================================================

PLANOS = {
    "prata": {
        "nome": "Acesso Prata",
        "valor": 10.00,
        "valor_exibicao": "10,00"
    },
    "ouro": {
        "nome": "Acesso Ouro",
        "valor": 15.00,
        "valor_exibicao": "15,00"
    }
}


def mp_token():
    token = os.environ.get(
        "MP_ACCESS_TOKEN",
        ""
    ).strip()

    if not token:
        raise RuntimeError(
            "MP_ACCESS_TOKEN nao configurado"
        )

    return token


def mercado_pago_headers():
    return {
        "Authorization": f"Bearer {mp_token()}",
        "Content-Type": "application/json"
    }


@app.route("/", methods=["GET", "POST"])
def home():

    if request.method == "GET":
        return render_template(
            "pay_simple.html"
        )

    nome = (
        request.form.get("name") or ""
    ).strip()[:80]

    email = (
        request.form.get("email") or ""
    ).strip().lower()[:150]

    plano_escolhido = (
        request.form.get("plano") or ""
    ).strip().lower()

    if not nome:
        return render_template(
            "pay_simple.html",
            error="Informe seu nome."
        ), 400

    if (
        "@" not in email
        or "." not in email.split("@")[-1]
    ):
        return render_template(
            "pay_simple.html",
            error="Informe um e-mail válido."
        ), 400

    # Verifica se o plano enviado realmente existe.
    if plano_escolhido not in PLANOS:
        return render_template(
            "pay_simple.html",
            error=(
                "Selecione o Acesso Prata "
                "ou o Acesso Ouro."
            )
        ), 400

    plano = PLANOS[plano_escolhido]

    valor = plano["valor"]
    nome_plano = plano["nome"]
    valor_exibicao = plano["valor_exibicao"]

    external_reference = (
        f"MDS-TI-{plano_escolhido.upper()}-"
        f"{uuid.uuid4().hex[:12]}"
    )

    payload = {
        "transaction_amount": valor,
        "description": nome_plano,
        "payment_method_id": "pix",
        "external_reference": external_reference,
        "payer": {
            "email": email,
            "first_name": nome
        }
    }

    headers = mercado_pago_headers()

    headers["X-Idempotency-Key"] = str(
        uuid.uuid4()
    )

    try:
        response = requests.post(
            f"{MP_API}/v1/payments",
            json=payload,
            headers=headers,
            timeout=20
        )

    except requests.RequestException:
        return render_template(
            "pay_simple.html",
            error=(
                "Não foi possível comunicar "
                "com o Mercado Pago."
            )
        ), 502

    try:
        data = response.json()

    except ValueError:
        return render_template(
            "pay_simple.html",
            error=(
                "O Mercado Pago retornou "
                "uma resposta inválida."
            )
        ), 502

    if response.status_code not in (
        200,
        201
    ):
        detalhe = data.get(
            "message",
            "Pagamento não criado."
        )

        causas = data.get("cause")

        if (
            isinstance(causas, list)
            and len(causas) > 0
            and isinstance(causas[0], dict)
        ):
            detalhe = (
                causas[0].get("description")
                or causas[0].get("code")
                or detalhe
            )

        return render_template(
            "pay_simple.html",
            error=f"Mercado Pago: {detalhe}"
        ), 400

    point_of_interaction = (
        data.get("point_of_interaction")
        or {}
    )

    transaction_data = (
        point_of_interaction.get(
            "transaction_data"
        )
        or {}
    )

    qr_code = (
        transaction_data.get("qr_code")
        or ""
    ).strip()

    qr_base64 = (
        transaction_data.get(
            "qr_code_base64"
        )
        or ""
    ).strip()

    payment_id = str(
        data.get("id")
        or ""
    ).strip()

    if not payment_id:
        return render_template(
            "message.html",
            title=(
                "Pagamento não identificado"
            ),
            message=(
                "O Mercado Pago não retornou "
                "a identificação do pagamento."
            )
        ), 502

    if not qr_code:
        return render_template(
            "message.html",
            title="Código Pix indisponível",
            message=(
                "O Mercado Pago não retornou "
                "o código Pix."
            )
        ), 502

    if not qr_base64:
        return render_template(
            "message.html",
            title="QR Code indisponível",
            message=(
                "O Mercado Pago não retornou "
                "a imagem do QR Code."
            )
        ), 502

    return render_template(
        "pix.html",
        amount=valor_exibicao,
        plano=nome_plano,
        plano_id=plano_escolhido,
        qr_code=qr_code,
        qr_base64=qr_base64,
        payment_id=payment_id
    )


@app.get("/api/status/<payment_id>")
def payment_status(payment_id):

    if not payment_id.isdigit():
        return jsonify({
            "ok": False,
            "error": (
                "ID do pagamento inválido."
            )
        }), 400

    try:
        response = requests.get(
            (
                f"{MP_API}/v1/payments/"
                f"{payment_id}"
            ),
            headers=mercado_pago_headers(),
            timeout=15
        )

    except requests.RequestException:
        return jsonify({
            "ok": False,
            "error": (
                "Não foi possível consultar "
                "o Mercado Pago."
            )
        }), 502

    try:
        data = response.json()

    except ValueError:
        return jsonify({
            "ok": False,
            "error": (
                "Resposta inválida "
                "do Mercado Pago."
            )
        }), 502

    if response.status_code != 200:
        return jsonify({
            "ok": False,
            "error": data.get(
                "message",
                "Pagamento não encontrado."
            )
        }), response.status_code

    transaction_details = (
        data.get("transaction_details")
        or {}
    )

    external_reference = (
        data.get("external_reference")
        or ""
    )

    plano = ""

    if "-PRATA-" in external_reference:
        plano = "prata"

    elif "-OURO-" in external_reference:
        plano = "ouro"

    return jsonify({
        "ok": True,
        "payment_id": str(
            data.get("id") or ""
        ),
        "status": data.get("status"),
        "status_detail": data.get(
            "status_detail"
        ),
        "transaction_amount": data.get(
            "transaction_amount"
        ),
        "net_received_amount": (
            transaction_details.get(
                "net_received_amount"
            )
        ),
        "date_approved": data.get(
            "date_approved"
        ),
        "plano": plano,
        "external_reference": external_reference
    }), 200


@app.get("/health")
def health():

    return jsonify({
        "ok": True,
        "time": datetime.now(
            timezone.utc
        ).isoformat()
    })


@app.errorhandler(404)
def page_not_found(error):

    return render_template(
        "message.html",
        title="Página não encontrada",
        message=(
            "O endereço acessado não existe."
        )
    ), 404


@app.errorhandler(500)
def internal_error(error):

    return render_template(
        "message.html",
        title="Erro interno",
        message=(
            "Não foi possível concluir "
            "a solicitação."
        )
    ), 500


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )

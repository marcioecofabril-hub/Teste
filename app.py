import hmac
import json
import os
import threading
import uuid
from datetime import datetime, timezone

import requests
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    session
)


# ============================================================
# APLICAÇÃO
# ============================================================

app = Flask(__name__)


# ============================================================
# LEITURA SEGURA DE VARIÁVEIS DE AMBIENTE
# ============================================================

def get_environment_value(variable_name):

    exact_value = os.environ.get(
        variable_name
    )

    if exact_value is not None:

        exact_value = str(
            exact_value
        ).strip()

        if exact_value:

            return exact_value

    normalized_name = (
        variable_name
        .strip()
        .upper()
    )

    for key, value in os.environ.items():

        normalized_key = (
            str(key)
            .strip()
            .upper()
        )

        if normalized_key != normalized_name:
            continue

        normalized_value = str(
            value or ""
        ).strip()

        if normalized_value:

            return normalized_value

    return ""


# ============================================================
# CHAVE DA SESSÃO FLASK
#
# O RENDER ORIGINAL USA SECRET_KEY.
# A APLICAÇÃO TAMBÉM ACEITA FLASK_SECRET_KEY.
# ============================================================

configured_flask_secret = (
    get_environment_value(
        "SECRET_KEY"
    )
    or get_environment_value(
        "FLASK_SECRET_KEY"
    )
)

app.secret_key = (
    configured_flask_secret
    or os.urandom(32)
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(
        os.environ.get(
            "RENDER"
        )
    )
)


# ============================================================
# CONFIGURAÇÕES
# ============================================================

MP_API = (
    "https://api.mercadopago.com"
)

PROMO_STATE_FILE = (
    get_environment_value(
        "PROMO_STATE_FILE"
    )
    or "promo_state.json"
)

PROMO_STATE_LOCK = (
    threading.Lock()
)


# ============================================================
# PLANOS NORMAIS
#
# ESTES PLANOS FICAM SEMPRE DISPONÍVEIS.
# ============================================================

PLANOS_NORMAIS = {
    "prata": {
        "nome": "Acesso Prata",
        "valor": 15.00,
        "valor_exibicao": "15,00",
        "descricao": "Acesso comum",
        "inclui_tivetv": False,
        "promocional": False
    },

    "ouro": {
        "nome": "Acesso Ouro",
        "valor": 20.00,
        "valor_exibicao": "20,00",
        "descricao": "Acesso Premium",
        "inclui_tivetv": False,
        "promocional": False
    }
}


# ============================================================
# PLANOS PROMOCIONAIS TRIMESTRAIS
#
# ESTES PLANOS APARECEM SOMENTE QUANDO A PROMOÇÃO
# ESTIVER ATIVADA.
# ============================================================

PLANOS_PROMOCIONAIS = {
    "prata_trimestral": {
        "nome": "Prata Trimestral",
        "valor": 40.00,
        "valor_exibicao": "40,00",
        "descricao": (
            "Acesso por 3 meses, "
            "sem licença do APP TiveTV"
        ),
        "inclui_tivetv": False,
        "promocional": True
    },

    "ouro_trimestral": {
        "nome": "Ouro Trimestral",
        "valor": 50.00,
        "valor_exibicao": "50,00",
        "descricao": (
            "Acesso por 3 meses, "
            "com licença do APP TiveTV"
        ),
        "inclui_tivetv": True,
        "promocional": True
    }
}


# ============================================================
# MERCADO PAGO
# ============================================================

def mp_token():

    token = get_environment_value(
        "MP_ACCESS_TOKEN"
    )

    if not token:

        raise RuntimeError(
            "MP_ACCESS_TOKEN não configurado"
        )

    return token


def mercado_pago_headers():

    return {
        "Authorization": (
            f"Bearer {mp_token()}"
        ),
        "Content-Type": (
            "application/json"
        )
    }


# ============================================================
# SENHA DA PROMOÇÃO
# ============================================================

def promotion_password():

    password = get_environment_value(
        "PROMO_PASSWORD"
    )

    if not password:

        raise RuntimeError(
            "PROMO_PASSWORD não configurada"
        )

    return password


# ============================================================
# ESTADO DA PROMOÇÃO
# ============================================================

def read_promotion_state():

    with PROMO_STATE_LOCK:

        try:

            with open(
                PROMO_STATE_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(
                    file
                )

                return bool(
                    data.get(
                        "active",
                        False
                    )
                )

        except (
            FileNotFoundError,
            json.JSONDecodeError,
            OSError,
            TypeError
        ):

            return False


def save_promotion_state(active):

    data = {
        "active": bool(
            active
        ),

        "updated_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    temporary_file = (
        f"{PROMO_STATE_FILE}.tmp"
    )

    with PROMO_STATE_LOCK:

        with open(
            temporary_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temporary_file,
            PROMO_STATE_FILE
        )


# ============================================================
# PLANOS DISPONÍVEIS
#
# PROMOÇÃO DESATIVADA:
# - PRATA R$ 15
# - OURO R$ 20
#
# PROMOÇÃO ATIVADA:
# - PRATA R$ 15
# - OURO R$ 20
# - PRATA TRIMESTRAL R$ 40
# - OURO TRIMESTRAL R$ 50
# ============================================================

def available_plans():

    plans = dict(
        PLANOS_NORMAIS
    )

    if read_promotion_state():

        plans.update(
            PLANOS_PROMOCIONAIS
        )

    return plans


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route(
    "/",
    methods=[
        "GET",
        "POST"
    ]
)
def home():

    promotion_active = (
        read_promotion_state()
    )

    admin_authenticated = bool(
        session.get(
            "promotion_admin",
            False
        )
    )

    if request.method == "GET":

        return render_template(
            "pay_simple.html",

            promotion_active=(
                promotion_active
            ),

            admin_authenticated=(
                admin_authenticated
            )
        )

    nome = (
        request.form.get(
            "name"
        )
        or ""
    ).strip()[:80]

    email = (
        request.form.get(
            "email"
        )
        or ""
    ).strip().lower()[:150]

    selected_plan = (
        request.form.get(
            "plano"
        )
        or ""
    ).strip().lower()

    template_data = {
        "promotion_active": (
            promotion_active
        ),

        "admin_authenticated": (
            admin_authenticated
        ),

        "nome": nome,

        "email": email,

        "selected_plan": (
            selected_plan
        )
    }

    if not nome:

        return render_template(
            "pay_simple.html",

            error=(
                "Informe seu nome."
            ),

            **template_data
        ), 400

    if (
        "@" not in email
        or "." not in email.split("@")[-1]
    ):

        return render_template(
            "pay_simple.html",

            error=(
                "Informe um e-mail válido."
            ),

            **template_data
        ), 400

    plans = available_plans()

    if selected_plan not in plans:

        return render_template(
            "pay_simple.html",

            error=(
                "O plano selecionado não está "
                "disponível neste momento."
            ),

            **template_data
        ), 400

    plan = plans[
        selected_plan
    ]

    value = plan[
        "valor"
    ]

    plan_name = plan[
        "nome"
    ]

    displayed_value = plan[
        "valor_exibicao"
    ]

    plan_description = plan[
        "descricao"
    ]

    includes_tivetv = plan[
        "inclui_tivetv"
    ]

    external_reference = (
        f"MDS-TI-"
        f"{selected_plan.upper()}-"
        f"{uuid.uuid4().hex[:12]}"
    )

    payload = {
        "transaction_amount": value,

        "description": (
            f"{plan_name} - "
            f"{plan_description}"
        ),

        "payment_method_id": "pix",

        "external_reference": (
            external_reference
        ),

        "payer": {
            "email": email,
            "first_name": nome
        },

        "metadata": {
            "cliente_nome": nome,

            "cliente_email": email,

            "plano_id": (
                selected_plan
            ),

            "plano_nome": (
                plan_name
            ),

            "promocional": (
                plan["promocional"]
            ),

            "inclui_tivetv": (
                includes_tivetv
            )
        }
    }

    try:

        headers = (
            mercado_pago_headers()
        )

    except RuntimeError as error:

        return render_template(
            "pay_simple.html",

            error=str(
                error
            ),

            **template_data
        ), 503

    headers[
        "X-Idempotency-Key"
    ] = str(
        uuid.uuid4()
    )

    try:

        response = requests.post(
            (
                f"{MP_API}"
                f"/v1/payments"
            ),

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
            ),

            **template_data
        ), 502

    try:

        data = response.json()

    except ValueError:

        return render_template(
            "pay_simple.html",

            error=(
                "O Mercado Pago retornou "
                "uma resposta inválida."
            ),

            **template_data
        ), 502

    if response.status_code not in (
        200,
        201
    ):

        detail = data.get(
            "message",
            "Pagamento não criado."
        )

        causes = data.get(
            "cause"
        )

        if (
            isinstance(
                causes,
                list
            )
            and causes
            and isinstance(
                causes[0],
                dict
            )
        ):

            detail = (
                causes[0].get(
                    "description"
                )
                or causes[0].get(
                    "code"
                )
                or detail
            )

        return render_template(
            "pay_simple.html",

            error=(
                f"Mercado Pago: {detail}"
            ),

            **template_data
        ), 400

    point_of_interaction = (
        data.get(
            "point_of_interaction"
        )
        or {}
    )

    transaction_data = (
        point_of_interaction.get(
            "transaction_data"
        )
        or {}
    )

    qr_code = (
        transaction_data.get(
            "qr_code"
        )
        or ""
    ).strip()

    qr_base64 = (
        transaction_data.get(
            "qr_code_base64"
        )
        or ""
    ).strip()

    payment_id = str(
        data.get(
            "id"
        )
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

            title=(
                "Código Pix indisponível"
            ),

            message=(
                "O Mercado Pago não retornou "
                "o código Pix."
            )
        ), 502

    if not qr_base64:

        return render_template(
            "message.html",

            title=(
                "QR Code indisponível"
            ),

            message=(
                "O Mercado Pago não retornou "
                "a imagem do QR Code."
            )
        ), 502

    return render_template(
        "pix.html",

        amount=(
            displayed_value
        ),

        plano=(
            plan_name
        ),

        descricao_plano=(
            plan_description
        ),

        inclui_tivetv=(
            includes_tivetv
        ),

        qr_code=(
            qr_code
        ),

        qr_base64=(
            qr_base64
        ),

        payment_id=(
            payment_id
        )
    )


# ============================================================
# LOGIN ADMINISTRATIVO
# ============================================================

@app.post(
    "/api/promotion/login"
)
def promotion_login():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    received_password = str(
        data.get(
            "password"
        )
        or ""
    ).strip()

    if not received_password:

        return jsonify({
            "ok": False,

            "error": (
                "Informe a senha."
            )
        }), 400

    try:

        configured_password = (
            promotion_password()
        )

    except RuntimeError as error:

        return jsonify({
            "ok": False,

            "error": str(
                error
            )
        }), 503

    if not hmac.compare_digest(
        received_password,
        configured_password
    ):

        return jsonify({
            "ok": False,

            "error": (
                "Senha incorreta."
            )
        }), 401

    session[
        "promotion_admin"
    ] = True

    session.permanent = False

    return jsonify({
        "ok": True,

        "active": (
            read_promotion_state()
        ),

        "message": (
            "Acesso administrativo liberado."
        )
    }), 200


# ============================================================
# ATIVAR OU DESATIVAR PROMOÇÃO
# ============================================================

@app.post(
    "/api/promotion/toggle"
)
def promotion_toggle():

    if not session.get(
        "promotion_admin",
        False
    ):

        return jsonify({
            "ok": False,

            "error": (
                "Acesso administrativo "
                "não autorizado."
            )
        }), 401

    current_state = (
        read_promotion_state()
    )

    new_state = not (
        current_state
    )

    try:

        save_promotion_state(
            new_state
        )

    except OSError as error:

        app.logger.error(
            (
                "Erro ao salvar o estado "
                "da promoção: %s"
            ),
            error
        )

        return jsonify({
            "ok": False,

            "error": (
                "Não foi possível salvar "
                "o estado da promoção."
            )
        }), 500

    return jsonify({
        "ok": True,

        "active": new_state,

        "message": (
            "Promoção ativada com sucesso."
            if new_state
            else
            "Promoção desativada com sucesso."
        )
    }), 200


# ============================================================
# SAIR DO CONTROLE ADMINISTRATIVO
# ============================================================

@app.post(
    "/api/promotion/logout"
)
def promotion_logout():

    session.pop(
        "promotion_admin",
        None
    )

    return jsonify({
        "ok": True
    }), 200


# ============================================================
# CONSULTAR ESTADO DA PROMOÇÃO
# ============================================================

@app.get(
    "/api/promotion/status"
)
def promotion_status():

    return jsonify({
        "ok": True,

        "active": (
            read_promotion_state()
        ),

        "admin_authenticated": bool(
            session.get(
                "promotion_admin",
                False
            )
        )
    }), 200


# ============================================================
# CONSULTAR STATUS DO PAGAMENTO
#
# IMPORTANTE:
# A ROTA PRECISA USAR <payment_id>.
# NÃO USE &lt;payment_id&gt;.
# ============================================================

@app.get(
    "/api/status/<payment_id>"
)
def payment_status(payment_id):

    if not payment_id.isdigit():

        return jsonify({
            "ok": False,

            "error": (
                "ID do pagamento inválido."
            )
        }), 400

    try:

        headers = (
            mercado_pago_headers()
        )

    except RuntimeError as error:

        return jsonify({
            "ok": False,

            "error": str(
                error
            )
        }), 503

    try:

        response = requests.get(
            (
                f"{MP_API}"
                f"/v1/payments/"
                f"{payment_id}"
            ),

            headers=headers,

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

    external_reference = (
        data.get(
            "external_reference"
        )
        or ""
    )

    if not external_reference.startswith(
        "MDS-TI-"
    ):

        return jsonify({
            "ok": False,

            "error": (
                "Pagamento não pertence "
                "a esta aplicação."
            )
        }), 403

    transaction_details = (
        data.get(
            "transaction_details"
        )
        or {}
    )

    metadata = (
        data.get(
            "metadata"
        )
        or {}
    )

    return jsonify({
        "ok": True,

        "payment_id": str(
            data.get(
                "id"
            )
            or ""
        ),

        "status": data.get(
            "status"
        ),

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

        "plano_id": metadata.get(
            "plano_id",
            ""
        ),

        "plano_nome": metadata.get(
            "plano_nome",
            ""
        ),

        "inclui_tivetv": bool(
            metadata.get(
                "inclui_tivetv",
                False
            )
        ),

        "external_reference": (
            external_reference
        )
    }), 200


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get(
    "/health"
)
def health():

    promo_password_exists = bool(
        get_environment_value(
            "PROMO_PASSWORD"
        )
    )

    secret_key_exists = bool(
        get_environment_value(
            "SECRET_KEY"
        )
        or get_environment_value(
            "FLASK_SECRET_KEY"
        )
    )

    mp_token_exists = bool(
        get_environment_value(
            "MP_ACCESS_TOKEN"
        )
    )

    return jsonify({
        "ok": True,

        "promotion_active": (
            read_promotion_state()
        ),

        "promo_password_exists": (
            promo_password_exists
        ),

        "secret_key_exists": (
            secret_key_exists
        ),

        "mp_token_exists": (
            mp_token_exists
        ),

        "time": datetime.now(
            timezone.utc
        ).isoformat()
    }), 200


# ============================================================
# ERRO 404
# ============================================================

@app.errorhandler(404)
def page_not_found(error):

    return render_template(
        "message.html",

        title=(
            "Página não encontrada"
        ),

        message=(
            "O endereço acessado não existe."
        )
    ), 404


# ============================================================
# ERRO 500
# ============================================================

@app.errorhandler(500)
def internal_error(error):

    app.logger.error(
        (
            "Erro interno da aplicação: %s"
        ),
        error
    )

    return render_template(
        "message.html",

        title=(
            "Erro interno"
        ),

        message=(
            "Não foi possível concluir "
            "a solicitação."
        )
    ), 500


# ============================================================
# INICIALIZAÇÃO
# ============================================================

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

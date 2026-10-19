
    <button id="btnGerar" onclick="ejecutarFluxoPythonWeb()">Gerar Teste e Enviar via WhatsApp</button>
    <div id="statusMsg" class="status">Status: Aguardando comando...</div>
</div>

<script>
function ejecutarFluxoPythonWeb() {
    const inputTelefone = document.getElementById('telefone').value.trim();
    const statusDiv = document.getElementById('statusMsg');
    const botao = document.getElementById('btnGerar');
    
    let numCliente = inputTelefone.replace(/\D/g, '');
    if (!numCliente) {
        alert("Por favor, digite o número do WhatsApp do cliente.");
        return;
    }

    botao.disabled = true;
    statusDiv.innerText = "Status: Gerando teste no painel...";
    statusDiv.style.color = "#f9e2af";

    fetch('/gerar-teste', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telefone: numCliente })
    })
    .then(res => res.json())
    .then(data => {
        if (data.sucesso) {
            statusDiv.innerText = "Status: Abrindo o WhatsApp...";
            statusDiv.style.color = "#a6e3a1";
            window.location.href = data.url_whatsapp;
            botao.disabled = false;
        } else {
            statusDiv.innerText = "Status: Erro verificado.";
            statusDiv.style.color = "#f38ba8";
            alert("ALERTA DO PAINEL:\\n" + data.erro);
            botao.disabled = false;
        }
    })
    .catch(err => {
        statusDiv.innerText = "Status: Falha na conexão com o Render.";
        statusDiv.style.color = "#f38ba8";
        botao.disabled = false;
    });
}
</script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_INTERFACE)

@app.route('/gerar-teste', methods=['POST'])
def gerar_teste():
    dados = request.get_json()
    num_cliente = dados.get('telefone', '').strip()
    
    num_cliente = re.sub(r"\D", "", num_cliente)
    if not num_cliente.startswith("55"):
        num_cliente = "55" + num_cliente

    # SEU LINK DE API DO CHATBOT ATUALIZADO SEM ERROS
    url_painel = "https://clubinfinity.info/api/chatbot/ayb1Bjp1PR/kg516V41jl"
    headers = { "User-Agent": "BotBot.Chat" }

    try:
        # O backend Python faz a busca segura simulando o comportamento local do seu computador
        resposta = requests.get(url_painel, headers=headers, timeout=12)
        
        if resposta.status_code == 200:
            texto_gerado = resposta.text
            
            if not texto_gerado or len(texto_gerado) < 10:
                return jsonify({"sucesso": False, "erro": "O painel respondeu um texto vazio. Verifique se possui créditos ativos!"})

            # Monta o redirecionamento com o texto de credenciais retornado na origem
            url_final_whatsapp = f"https://wa.me{num_cliente}?text={requests.utils.quote(texto_gerado)}"
            return jsonify({"sucesso": True, "url_whatsapp": url_final_whatsapp})
        else:
            return jsonify({"sucesso": False, "erro": f"Código HTTP {resposta.status_code} recebido do painel."})

    except Exception as e:
        return jsonify({"sucesso": False, "erro": f"Não foi possível conectar ao link: {str(e)}"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

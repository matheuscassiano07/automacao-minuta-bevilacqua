from flask import Flask, request, render_template, send_file, redirect, jsonify, after_this_request
import os
import subprocess
import re  # Importação necessária para limpar as tags
from num2words import num2words 
from threading import Lock
import urllib.request
import zipfile
import json

app = Flask(__name__)

# --- FUNÇÕES AUXILIARES DE LÓGICA ---
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
PROPOSTA_STORE = {}
PROPOSTA_STORE_LOCK = Lock()
PROPOSTA_STORE_FILE = os.path.join(os.path.dirname(__file__), "proposta_store.json")
TECTONIC_VERSION = "0.15.0"
TECTONIC_URL = f"https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40{TECTONIC_VERSION}/tectonic-{TECTONIC_VERSION}-x86_64-pc-windows-msvc.zip"
TECTONIC_DIR = os.path.join(os.path.dirname(__file__), ".tectonic")
TECTONIC_EXE = os.path.join(TECTONIC_DIR, "tectonic.exe")

def carregar_store_propostas():
    if not os.path.exists(PROPOSTA_STORE_FILE):
        return
    try:
        with open(PROPOSTA_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                PROPOSTA_STORE.update(data)
    except Exception:
        pass

def salvar_store_propostas():
    try:
        with open(PROPOSTA_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(PROPOSTA_STORE, f, ensure_ascii=False)
    except Exception:
        pass

def formatar_moeda(valor_float):
    """Transforma o número do Python (16000.0) em texto padrão BR (16.000,00)"""
    return f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def gerar_extenso(valor_float):
    """Gera o texto (ex: dezesseis mil) e retira a palavra 'reais' para encaixar no LaTeX"""
    extenso = num2words(valor_float, lang='pt_BR', to='currency')
    return extenso.replace(' reais', '').replace(' real', '').replace(' centavos', '')

def limpar_citacoes(texto_latex):
    """Varre o LaTeX e apaga todas as tags que o usuário esqueceu de tirar"""
    # Regex que encontra [cite: 1] ou [cite: 1, 2, 3] e apaga
    return re.sub(r'\[cite:[^\]]+\]', '', texto_latex)

def montar_dados_requisicao(origem):
    """Monta os dados tipados e já calculados para PDF e proposta web."""
    nome_cliente = origem.get('nome_cliente')
    cpf = origem.get('cpf')
    cidade = origem.get('cidade')
    condominio = origem.get('condominio')
    data_dia = origem.get('data_dia')
    data_mes = origem.get('data_mes')
    data_ano = origem.get('data_ano')

    metragem_raw = origem.get('metragem', '')
    valor_m2_raw = origem.get('valor_m2', '')
    metragem_str = metragem_raw.replace(',', '.')
    valor_m2_str = valor_m2_raw.replace(',', '.')

    metragem_num = float(metragem_str)
    valor_m2_num = float(valor_m2_str)
    valor_total_num = metragem_num * valor_m2_num
    valor_parcela_num = valor_total_num * 0.20

    return {
        "nome_cliente": nome_cliente,
        "cpf": cpf,
        "cidade": cidade,
        "condominio": condominio,
        "data_dia": data_dia,
        "data_mes": data_mes,
        "data_ano": data_ano,
        "metragem_raw": metragem_raw,
        "valor_m2_num": valor_m2_num,
        "valor_total_num": valor_total_num,
        "valor_parcela_num": valor_parcela_num
    }

def gerar_pdf_com_dados(dados_base):
    """Gera o PDF do contrato com base nos dados fornecidos."""
    dados_latex = {
        '[[NOMECLIENTE]]': dados_base["nome_cliente"],
        '[[CPF]]': dados_base["cpf"],
        '[[METRAGEM]]': dados_base["metragem_raw"],
        '[[CIDADE]]': dados_base["cidade"],
        '[[CONDOMINIO]]': dados_base["condominio"],
        '[[VALORM2]]': formatar_moeda(dados_base["valor_m2_num"]),
        '[[VALORM2EXT]]': gerar_extenso(dados_base["valor_m2_num"]),
        '[[VALORTOTAL]]': formatar_moeda(dados_base["valor_total_num"]),
        '[[VALORTOTALEXT]]': gerar_extenso(dados_base["valor_total_num"]),
        '[[VALORPARCELA]]': formatar_moeda(dados_base["valor_parcela_num"]),
        '[[VALORPARCELAEXT]]': gerar_extenso(dados_base["valor_parcela_num"]),
        '[[DATADIA]]': dados_base["data_dia"],
        '[[DATAMES]]': dados_base["data_mes"],
        '[[DATAANO]]': dados_base["data_ano"]
    }

    with open('contrato_template.tex', 'r', encoding='utf-8') as file:
        conteudo_contrato = file.read()

    conteudo_contrato = limpar_citacoes(conteudo_contrato)

    for tag, valor in dados_latex.items():
        if valor:
            valor_seguro = str(valor).replace('%', '\\%').replace('$', '\\$')
            conteudo_contrato = conteudo_contrato.replace(tag, valor_seguro)

    nome_tex = 'temp_contrato.tex'
    nome_pdf = 'temp_contrato.pdf'
    with open(nome_tex, 'w', encoding='utf-8') as file:
        file.write(conteudo_contrato)

    subprocess.run([obter_tectonic(), nome_tex, '--outdir', '.'], check=True, stdout=subprocess.DEVNULL)
    return nome_pdf

def obter_tectonic():
    """Baixa o Tectonic automaticamente se não existir localmente."""
    if os.path.exists(TECTONIC_EXE):
        return TECTONIC_EXE

    os.makedirs(TECTONIC_DIR, exist_ok=True)
    zip_path = os.path.join(TECTONIC_DIR, "tectonic.zip")
    urllib.request.urlretrieve(TECTONIC_URL, zip_path)

    with zipfile.ZipFile(zip_path, 'r') as archive:
        archive.extractall(TECTONIC_DIR)

    if os.path.exists(zip_path):
        os.remove(zip_path)

    if not os.path.exists(TECTONIC_EXE):
        raise FileNotFoundError("Falha ao preparar o compilador LaTeX automático (Tectonic).")

    return TECTONIC_EXE

def agendar_limpeza_temp():
    @after_this_request
    def cleanup(response):
        extensoes_para_limpar = ['.tex', '.aux', '.log', '.out', '.pdf']
        for ext in extensoes_para_limpar:
            arquivo_limpar = f"temp_contrato{ext}"
            if os.path.exists(arquivo_limpar):
                try:
                    os.remove(arquivo_limpar)
                except OSError:
                    pass
        return response

def slugify_cliente(nome):
    base = (nome or "cliente").strip().lower()
    mapa = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçñ", "aaaaaeeeeiiiiooooouuuucn")
    base = base.translate(mapa)
    base = re.sub(r'[^a-z0-9]+', '-', base)
    base = re.sub(r'-+', '-', base).strip('-')
    return base or "cliente"

def payload_para_link(dados_base):
    return {
        "nome_cliente": dados_base["nome_cliente"] or "",
        "cpf": dados_base["cpf"] or "",
        "cidade": dados_base["cidade"] or "",
        "condominio": dados_base["condominio"] or "",
        "metragem": dados_base["metragem_raw"] or "",
        "valor_m2": formatar_moeda(dados_base["valor_m2_num"]),
        "data_dia": dados_base["data_dia"] or "",
        "data_mes": dados_base["data_mes"] or "",
        "data_ano": dados_base["data_ano"] or ""
    }

def construir_url_compartilhamento(payload):
    slug = slugify_cliente(payload.get("nome_cliente", "cliente"))
    with PROPOSTA_STORE_LOCK:
        PROPOSTA_STORE[slug] = payload
        salvar_store_propostas()
    return f"{FRONTEND_URL}/proposta/{slug}"

def construir_url_proposta(dados_base):
    """Constrói URL do frontend com todos os dados personalizados."""
    payload = payload_para_link(dados_base)
    slug = slugify_cliente(payload.get("nome_cliente", "cliente"))
    with PROPOSTA_STORE_LOCK:
        PROPOSTA_STORE[slug] = payload
        salvar_store_propostas()
    return f"{FRONTEND_URL}/apresentacao/{slug}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/gerar', methods=['POST'])
def gerar_contrato():
    try:
        dados_base = montar_dados_requisicao(request.form)
        nome_pdf = gerar_pdf_com_dados(dados_base)
        nome_download = f"Contrato_{dados_base['nome_cliente']}.pdf"
        agendar_limpeza_temp()
        return send_file(nome_pdf, as_attachment=True, download_name=nome_download)
    except subprocess.CalledProcessError:
        return "Erro interno: Falha ao compilar o LaTeX. O PDF não pôde ser gerado."
    except ValueError:
        return "Erro de digitação: Certifique-se de digitar apenas números (ex: 80,00) nos campos de Metragem e Valor M²."
    except FileNotFoundError:
        return "Erro interno: Falha ao preparar o compilador automático da minuta."
    except Exception as e:
        return f"Ocorreu um erro inesperado: {str(e)}"

@app.route('/minuta', methods=['POST'])
def visualizar_minuta():
    try:
        dados_base = montar_dados_requisicao(request.form)
        nome_pdf = gerar_pdf_com_dados(dados_base)
        agendar_limpeza_temp()
        return send_file(nome_pdf, as_attachment=False, download_name="minuta.pdf")
    except subprocess.CalledProcessError:
        return "Erro interno: Falha ao compilar o LaTeX. O PDF não pôde ser gerado."
    except ValueError:
        return "Erro de digitação: Certifique-se de digitar apenas números (ex: 80,00) nos campos de Metragem e Valor M²."
    except FileNotFoundError:
        return "Erro interno: Falha ao preparar o compilador automático da minuta."
    except Exception as e:
        return f"Ocorreu um erro inesperado: {str(e)}"

@app.route('/gerar-pdf', methods=['GET'])
def gerar_contrato_por_query():
    try:
        dados_base = montar_dados_requisicao(request.args)
        nome_pdf = gerar_pdf_com_dados(dados_base)
        nome_download = f"Contrato_{dados_base['nome_cliente']}.pdf"
        agendar_limpeza_temp()
        return send_file(nome_pdf, as_attachment=True, download_name=nome_download)
    except subprocess.CalledProcessError:
        return "Erro interno: Falha ao compilar o LaTeX. O PDF não pôde ser gerado."
    except ValueError:
        return "Erro de digitação: Certifique-se de digitar apenas números (ex: 80,00) nos campos de Metragem e Valor M²."
    except FileNotFoundError:
        return "Erro interno: Falha ao preparar o compilador automático da minuta."
    except Exception as e:
        return f"Ocorreu um erro inesperado: {str(e)}"

@app.route('/proposta', methods=['POST'])
def abrir_proposta_frontend():
    try:
        dados_base = montar_dados_requisicao(request.form)
        return redirect(construir_url_proposta(dados_base))
    except ValueError:
        return "Erro de digitação: Certifique-se de digitar apenas números (ex: 80,00) nos campos de Metragem e Valor M²."

@app.route('/gerar-link-cliente', methods=['POST'])
def gerar_link_cliente():
    try:
        payload = request.get_json(silent=True) or {}
        if not payload.get("nome_cliente"):
            return jsonify({"erro": "nome_cliente é obrigatório"}), 400
        link = construir_url_compartilhamento(payload)
        return jsonify({"url": link})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/proposta-dados/<slug>', methods=['GET'])
def obter_dados_proposta(slug):
    with PROPOSTA_STORE_LOCK:
        payload = PROPOSTA_STORE.get(slug)
    if not payload:
        return jsonify({"erro": "proposta não encontrada"}), 404
    return jsonify(payload)

if __name__ == '__main__':
    carregar_store_propostas()
    app.run(debug=True, port=5000)
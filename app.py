from flask import Flask, request, render_template, send_file
import os
import subprocess
import re  # Importação necessária para limpar as tags
from num2words import num2words 

app = Flask(__name__)

# --- FUNÇÕES AUXILIARES DE LÓGICA ---
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/gerar', methods=['POST'])
def gerar_contrato():
    try:
        # 1. Pegar os dados de texto digitados
        nome_cliente = request.form.get('nome_cliente')
        cpf = request.form.get('cpf')
        cidade = request.form.get('cidade')
        condominio = request.form.get('condominio')
        data_dia = request.form.get('data_dia')
        data_mes = request.form.get('data_mes')
        data_ano = request.form.get('data_ano')

        # 2. LÓGICA MATEMÁTICA
        metragem_str = request.form.get('metragem').replace(',', '.')
        valor_m2_str = request.form.get('valor_m2').replace(',', '.')
        
        metragem_num = float(metragem_str)
        valor_m2_num = float(valor_m2_str)

        valor_total_num = metragem_num * valor_m2_num
        valor_parcela_num = valor_total_num * 0.20 # Calcula 20%

        # 3. Preparando os dados finais para substituir no LaTeX
        dados = {
            '[[NOMECLIENTE]]': nome_cliente,
            '[[CPF]]': cpf,
            '[[METRAGEM]]': request.form.get('metragem'), 
            '[[CIDADE]]': cidade,
            '[[CONDOMINIO]]': condominio,
            '[[VALORM2]]': formatar_moeda(valor_m2_num),
            '[[VALORM2EXT]]': gerar_extenso(valor_m2_num),
            '[[VALORTOTAL]]': formatar_moeda(valor_total_num),
            '[[VALORTOTALEXT]]': gerar_extenso(valor_total_num),
            '[[VALORPARCELA]]': formatar_moeda(valor_parcela_num),
            '[[VALORPARCELAEXT]]': gerar_extenso(valor_parcela_num),
            '[[DATADIA]]': data_dia,
            '[[DATAMES]]': data_mes,
            '[[DATAANO]]': data_ano
        }

        # 4. Ler o modelo e processar
        with open('contrato_template.tex', 'r', encoding='utf-8') as file:
            conteudo_contrato = file.read()

        # A MÁGICA DE LIMPEZA ACONTECE AQUI:
        conteudo_contrato = limpar_citacoes(conteudo_contrato)

        for tag, valor in dados.items():
            if valor:
                # Converte para string e protege caracteres especiais (%, $)
                valor_seguro = str(valor).replace('%', '\\%').replace('$', '\\$')
                conteudo_contrato = conteudo_contrato.replace(tag, valor_seguro)

        # 5. Salvar e compilar o PDF
        nome_tex = 'temp_contrato.tex'
        nome_pdf = 'temp_contrato.pdf'
        
        with open(nome_tex, 'w', encoding='utf-8') as file:
            file.write(conteudo_contrato)

        subprocess.run(['pdflatex', '-interaction=nonstopmode', nome_tex], check=True, stdout=subprocess.DEVNULL)
        
        # 6. Retornar PDF 
        nome_download = f"Contrato_{nome_cliente}.pdf"
        return send_file(nome_pdf, as_attachment=True, download_name=nome_download)
        
    except subprocess.CalledProcessError:
        return "Erro interno: Falha ao compilar o LaTeX. O PDF não pôde ser gerado."
    except ValueError:
        return "Erro de digitação: Certifique-se de digitar apenas números (ex: 80,00) nos campos de Metragem e Valor M²."
    except Exception as e:
        return f"Ocorreu um erro inesperado: {str(e)}"
    finally:
        # Limpa o lixo que o LaTeX gera
        extensoes_para_limpar = ['.tex', '.aux', '.log', '.out']
        for ext in extensoes_para_limpar:
            arquivo_limpar = f"temp_contrato{ext}"
            if os.path.exists(arquivo_limpar):
                os.remove(arquivo_limpar)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
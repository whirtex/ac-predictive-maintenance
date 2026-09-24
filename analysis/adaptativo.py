"""Detector adaptativo: aprende o normal no lugar e vai se atualizando.

Um modelo treinado uma vez so fica velho quando o lugar ou as condicoes
mudam. Na bancada, o mesmo ventilador vibrou ~0,15 g numa mesa e
~0,10 g em outra, uma diferenca maior que a de uma obstrucao. E o
motor aquecendo muda a vibracao devagar por mais de 20 minutos.

Por isso este detector:

  1. passa APRENDIZADO_S aprendendo o normal do lugar onde esta;
  2. depois detecta. Cada janela passa por duas perguntas, e basta uma
     dizer que nao esta normal para virar alarme:
       - o Isolation Forest, sobre as 5 medidas totais (formato.TOTAIS),
         responde se a combinacao parece com o normal;
       - a regua responde se a vibracao total, o pico ou a forca da
         frequencia dominante se afastaram mais de REGUA desvios do
         normal. O Isolation Forest diz se um ponto e estranho, mas nao
         quao estranho: longe do normal, a nota dele satura, e uma
         vibracao 30% mais forte chegou a ficar colada no limiar;
     O Isolation Forest sozinho so vira alarme se marcar duas janelas
     seguidas e se alguma medida estiver a pelo menos Z_MINIMO_MODELO
     desvios do normal. Ao vivo, com o normal aprendido muito apertado,
     ele acusava oscilacoes de 1,7 a 2,8 desvios, do tamanho do ruido. A regua dispara na hora, porque pega os impactos fortes;
  3. a cada ATUALIZA_S, reaprende com os ultimos MEMORIA_S de janelas
     normais. Mudanca lenta, como o aquecimento ou o clima do dia, entra
     no normal. Mudanca rapida, como uma obstrucao, vira alarme.

O risco de quem se adapta e se acostumar com uma falha que cresce
devagar. As protecoes:

  - janela marcada como anomala nunca entra no normal, nem as dos
    BLOQUEIO_S seguintes a um alarme;
  - enquanto houver alarme recente, o modelo nao se atualiza;
  - os ultimos ATRASO_S ficam fora de cada reaprendizado, para o comeco
    de uma falha, antes de ser marcado, nao entrar no normal;
  - a referencia do primeiro aprendizado fica guardada, e o detector
    informa quanto o normal atual ja se afastou dela (deriva). Um
    desgaste lento aparece ai, mesmo que o modelo tenha se acostumado.

O sistema sozinho nao distingue uma falha persistente de uma mudanca
legitima de posicao. Apos 3 minutos de alarme persistente, ele pede
investigacao e mantem a referencia anterior. A adaptacao automatica
continua apenas com leituras consideradas normais.
"""

from collections import deque

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from formato import TOTAIS, derivar_janela, nome_legivel

APRENDIZADO_S = 120    # aprendizado inicial no lugar
ATUALIZA_S = 60        # de quanto em quanto tempo reaprende
MEMORIA_S = 600        # quanto do passado recente entra no normal
BLOQUEIO_S = 30        # depois de um alarme, nao aprende por esse tempo
ATRASO_S = 30          # o passado mais recente fica fora do reaprendizado
QUANTIL = 0.002        # fracao do normal recente que ficaria abaixo do limiar
REGUA = 6              # desvios que a regua tolera
Z_MINIMO_MODELO = 3    # o modelo so acusa se alguma medida passar disso
PISO = 0.03            # o desvio nunca conta como menor que 3% da media
MINIMO_JANELAS = 40    # abaixo disso nao ha dado suficiente para treinar
PERSISTENCIA_S = 180   # tempo minimo antes de pedir investigacao
FRACAO_PERSISTENTE = 0.8  # fracao minima de janelas em alerta nesse tempo
MINIMO_JANELAS_PERSISTENCIA = 100
INTERVALO_SEM_ALERTA_S = 10  # pausa maior encerra o episodio persistente
PARTIDA_S = 15         # comeco de cada aprendizado do zero fica de fora: e a
                       # partida do motor, com trancos que alargam o normal

# Medidas que a regua vigia: as de intensidade. Curtose e frequencia
# ficam so com o Isolation Forest.
MEDIDAS_REGUA = ["rms_total", "pico_total", "adom_total"]


def descrever(chave, z, valor, media):
    """Frase curta sobre o quanto uma medida se afastou do normal.

    Longe do normal, desvios viram numeros sem sentido (uma batida leva a
    curtose de 2 para 90, ou mais de mil desvios); ai a frase usa quantas
    vezes o normal.
    """
    nome = nome_legivel(chave)
    if abs(z) > 20 and media > 0:
        vezes = valor / media
        texto = f"{nome}: {vezes:.1f} vezes o normal" if vezes >= 1 else \
                f"{nome}: {100 * (1 - vezes):.0f}% abaixo do normal"
    else:
        sentido = "acima" if z > 0 else "abaixo"
        texto = f"{nome}: {abs(z):.1f} desvios {sentido} do normal"
    return texto.replace(".", ",")


class DetectorAdaptativo:
    def __init__(self, aprendizado_s=APRENDIZADO_S, atualiza_s=ATUALIZA_S,
                 memoria_s=MEMORIA_S, bloqueio_s=BLOQUEIO_S, quantil=QUANTIL):
        self.aprendizado_s = aprendizado_s
        self.atualiza_s = atualiza_s
        self.memoria_s = memoria_s
        self.bloqueio_s = bloqueio_s
        self.quantil = quantil
        self.janelas = deque()   # [t, medidas, pode_aprender]
        self.modelo = None
        self.inicio = None
        self.ultima_atualizacao = None
        self.bloqueio_ate = float("-inf")
        self.referencia = None   # vibracao total media do primeiro aprendizado
        self.atualizacoes = []   # uma entrada por (re)aprendizado
        self.modelo_anterior = False   # o Isolation Forest marcou a janela anterior?
        self.inicio_alerta = None
        self.ultimo_alerta = None
        self.alertas_recentes = deque()  # (t, fora), durante a mudanca persistente
        self.investigar = False

    def _mudanca_persistente(self, t, fora):
        """Sinaliza uma unica vez quando um alarme exige investigacao."""
        if fora:
            if self.inicio_alerta is None:
                self.inicio_alerta = t
            self.ultimo_alerta = t
        elif self.ultimo_alerta is not None and t - self.ultimo_alerta > INTERVALO_SEM_ALERTA_S:
            self.inicio_alerta = None
            self.ultimo_alerta = None
            self.alertas_recentes.clear()
            self.investigar = False

        if self.inicio_alerta is None:
            return False
        self.alertas_recentes.append((t, fora))
        while self.alertas_recentes and self.alertas_recentes[0][0] < t - PERSISTENCIA_S:
            self.alertas_recentes.popleft()
        persistente = (fora and t - self.inicio_alerta >= PERSISTENCIA_S
                       and len(self.alertas_recentes) >= MINIMO_JANELAS_PERSISTENCIA
                       and sum(alarme for _, alarme in self.alertas_recentes)
                       / len(self.alertas_recentes) >= FRACAO_PERSISTENTE)
        nova_escalada = persistente and not self.investigar
        if persistente:
            self.investigar = True
        return nova_escalada

    def _treinar(self, t):
        uteis = [x for tt, x, ok in self.janelas
                 if ok and t - self.memoria_s <= tt <= t - ATRASO_S]
        if self.modelo is None:
            # no aprendizado do zero ainda nao ha alarme: usa tudo menos a partida
            uteis = [x for tt, x, ok in self.janelas if ok]
        if len(uteis) < MINIMO_JANELAS:
            return False
        tabela = pd.DataFrame(uteis, columns=TOTAIS)
        escala = StandardScaler().fit(tabela)
        floresta = IsolationForest(n_estimators=150, random_state=0)
        floresta.fit(escala.transform(tabela))
        pontos = floresta.score_samples(escala.transform(tabela))
        # Centro e variacao robustos: mediana e desvio absoluto mediano
        # (MAD, convertido para a escala do desvio padrao). Um trecho curto
        # de trancos, como a partida do motor, nao desloca a mediana nem
        # alarga o MAD, ao contrario da media e do desvio padrao: ao vivo,
        # a partida no aprendizado deixou a regua 51% acima do normal.
        media = tabela.median()
        mad = 1.4826 * (tabela - media).abs().median()
        desvio = np.maximum(mad.fillna(0), PISO * media.abs())
        anterior = self.modelo["rms_media"] if self.modelo else None
        tipo = "atualizacao" if self.modelo else "inicial"
        self.modelo = {
            "escala": escala,
            "floresta": floresta,
            "limiar": float(np.quantile(pontos, self.quantil)),
            "media": media,
            "desvio": desvio.replace(0, np.nan),
            "rms_media": float(media["rms_total"]),
            "rms_desvio": float(mad["rms_total"]),
        }
        if self.referencia is None:
            self.referencia = self.modelo["rms_media"]
        self.ultima_atualizacao = t
        self.atualizacoes.append({
            "t": t,
            "tipo": tipo,
            "rms_media": self.modelo["rms_media"],
            "rms_desvio": self.modelo["rms_desvio"],
            "regua": self.modelo["rms_media"] + REGUA * float(desvio["rms_total"]),
            "limite": -self.modelo["limiar"],
            "janelas": len(uteis),
            "mudanca": None if anterior is None else 100 * (self.modelo["rms_media"] / anterior - 1),
            "deriva": 100 * (self.modelo["rms_media"] / self.referencia - 1),
        })
        return True

    def _podar(self, t):
        while self.janelas and self.janelas[0][0] < t - self.memoria_s:
            self.janelas.popleft()

    def adicionar(self, t, janela):
        """Recebe uma janela (dicionario com as colunas do CSV) no instante t.

        Devolve um dicionario com a fase ('aprendendo' ou 'detectando') e,
        na deteccao, se a janela esta fora do normal, o grau de anomalia,
        o limite, a medida mais afastada e a deriva desde a instalacao.
        """
        medidas = derivar_janela(janela)
        x = [medidas[c] for c in TOTAIS]
        if self.inicio is None:
            self.inicio = t

        if self.modelo is None:
            self.janelas.append([t, x, t - self.inicio >= PARTIDA_S])
            self._podar(t)
            if t - self.inicio >= self.aprendizado_s:
                self._treinar(t)
            return {"fase": "aprendendo", "medidas": medidas,
                    "falta": max(0.0, self.aprendizado_s - (t - self.inicio))}

        m = self.modelo
        tabela = pd.DataFrame([x], columns=TOTAIS)
        pontuacao = float(m["floresta"].score_samples(m["escala"].transform(tabela))[0])
        z = ((tabela.iloc[0] - m["media"]) / m["desvio"]).fillna(0)
        modelo_agora = pontuacao < m["limiar"]
        pelo_modelo = (modelo_agora and self.modelo_anterior
                       and bool((z.abs() >= Z_MINIMO_MODELO).any()))
        self.modelo_anterior = modelo_agora
        pela_regua = bool((z[MEDIDAS_REGUA].abs() > REGUA).any())
        fora = pelo_modelo or pela_regua
        motivo = " e ".join(n for n, v in (("modelo", pelo_modelo), ("régua", pela_regua)) if v)

        # O texto mostra a medida que disparou: se foi a regua, a mais
        # afastada entre as que ela vigia; se foi so o modelo, a mais
        # afastada de todas.
        candidatas = z[MEDIDAS_REGUA] if pela_regua else z
        chave = candidatas.abs().idxmax()
        detalhe = descrever(chave, z[chave], medidas[chave], m["media"][chave])

        if fora:
            self.bloqueio_ate = t + self.bloqueio_s
        nova_escalada = self._mudanca_persistente(t, fora)
        # So o que virou alarme fica fora do normal. Uma mudanca pequena, que
        # o modelo estranha mas nao chega a alarme, entra e e absorvida:
        # antes, o ventilador solto que mudou 5% de posicao ficava minutos
        # sendo acusado sem nunca ser aprendido.
        self.janelas.append([t, x, (not fora) and t >= self.bloqueio_ate])
        self._podar(t)
        if t - self.ultima_atualizacao >= self.atualiza_s and t >= self.bloqueio_ate:
            self._treinar(t)

        return {
            "fase": "detectando",
            "medidas": medidas,
            "fora": fora,
            "investigar": self.investigar,
            "nova_escalada": nova_escalada,
            "tempo_alerta_s": t - self.inicio_alerta if self.investigar else None,
            "motivo": motivo,
            "anomalia": -pontuacao,
            "limite": -m["limiar"],
            "detalhe": detalhe,
            "rms_media": m["rms_media"],
            "rms_desvio": m["rms_desvio"],
            "regua": m["rms_media"] + REGUA * float(m["desvio"]["rms_total"]),
            "deriva": 100 * (m["rms_media"] / self.referencia - 1),
        }

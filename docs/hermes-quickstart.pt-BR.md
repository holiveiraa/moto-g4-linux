# Hermes no Moto: do setup à primeira conversa

O app transforma o Moto em um companheiro com rosto animado e voz. Ele usa
**seu Hermes Agent já existente**, sem criar outro bot e sem substituir o
terminal. Este roteiro configura a conexão; a instalação do Linux e o build
do app são etapas anteriores, descritas nos guias vinculados abaixo.

**Estado:** experimental, instalado no Moto XT1640 de referência. O fluxo
completo passou com Groq, Hermes e Edge reais, incluindo a ativação e uma pergunta
sintéticas reproduzidas acusticamente pelo alto-falante e captadas pelo microfone.
Depois da resposta, ficou 60 segundos na escuta sem novo envio. Sua voz e a
robustez no seu ambiente ainda precisam de validação. Não há instalador universal.

## 1. Confira o que você precisa

| Onde | Requisito |
| --- | --- |
| Moto | Linux deste projeto funcionando, Wi-Fi, microfone/alto-falante e os componentes do app instalados. |
| Hermes | Sua instância existente, um perfil combinado e APIs compatíveis. O cliente foi desenvolvido para Hermes v0.22.4/Umbrel 2.0. |
| Transcrição | Sua chave Groq cadastrada privadamente no Moto. Não publique nem envie a chave pelo chat. |
| Resposta falada | Edge TTS preparado dentro do próprio Hermes, com uma voz pt-BR disponível. |
| Acesso | Origem do **app Hermes**: HTTPS, ou HTTP pelo IP numérico Tailscale com a VPN conectada no Moto. Conta Umbrel e senha; 2FA só se habilitado. |

Se está começando com outro telefone, use primeiro o
[guia de instalação por agente](agent-installation.md). Se a base Linux já
funciona, peça ao agente do Moto para seguir o
[build e instalação do app](hermes-setup.md#build-from-public-source), incluindo
o modelo local de ativação. Não use um rootfs configurado de outra pessoa.

## 2. Envie estas instruções ao próprio Hermes

Você pode enviar a mensagem pela interface que já utiliza, inclusive Telegram:

> Prepare sua parte para meu app do Moto usando
> https://github.com/holiveiraa/moto-g4-linux. Leia AGENTS.md,
> docs/hermes-server-agent.md e docs/hermes-setup.md. Trabalhe somente dentro
> do próprio app/runtime e dos dados do perfil Hermes. Confira sua versão e
> as APIs de chat/áudio existentes, faça backup da configuração e prepare Edge
> TTS com uma voz pt-BR, preservando meu Telegram. Nunca acesse nem altere o
> host do Umbrel, Docker, gateway, autenticação, portas ou serviços. Informe o
> perfil e a voz escolhidos, os testes feitos e qualquer impedimento dentro
> desse limite. Não declare concluído o teste de voz no Moto antes de fazê-lo.

O [guia para o Hermes servidor](hermes-server-agent.md) é a instrução técnica
que ele deve seguir. O trabalho é no próprio ambiente/perfil Hermes: verificar
as APIs existentes e preparar a síntese de voz. **Não há plugin adicional
obrigatório** para o contrato já implementado. Se a versão diferir, o Hermes
deve apontar a incompatibilidade sem abrir porta interna nem remover o login.

Guarde a resposta dele com **versão, nome do perfil e voz**. O mesmo perfil
precisa atender chat e áudio. Se uma mudança no perfil atual afetar o Telegram,
combine um perfil separado usando os recursos suportados pelo seu Hermes.

## 3. Configure a chave de transcrição no Moto

Abra **Painel → Voz e áudio → Groq** e cadastre **sua própria chave** nos campos
privados do telefone. O app usa essa mesma configuração do ditado; não é
necessário duplicar a chave dentro do Hermes servidor.

O áudio de espera por “Olá Hermes” é processado localmente e descartado.
Depois da confirmação falada, cada fala da conversa é enviada à Groq para
transcrição. A fala de resposta usa o serviço online Edge a partir do Hermes.

## 4. Preencha a conexão no app

Abra **Painel → Hermes → ··· → Configurar**. Segurar o rosto também abre as
opções. A configuração inicial exige toque e teclado; depois do login, a
conversa normal é por voz.

| Campo/opção | O que preencher |
| --- | --- |
| URL do Hermes | A **origem do app**: `https://server.example:8443`, ou HTTP pelo IP Tailscale, como `http://100.64.0.10:18790` (exemplos fictícios). Não inclua caminho, senha, token ou parâmetros nem use uma porta interna de container. |
| Conta Umbrel | O identificador da conta com acesso ao app; `0` é a conta proprietária no contrato inspecionado. |
| Perfil Hermes | O perfil confirmado pelo próprio Hermes. Deixe o padrão somente se ele confirmou que é esse mesmo. |
| Origem do login Umbrel | Normalmente vazia: o cliente usa o mesmo esquema/endereço na porta 2000. Outra origem precisa ser exata, permitida e verificada. |
| CA adicional | Vazia se o certificado já for confiável no sistema. Para CA privada, use o caminho de um PEM obtido e conferido independentemente. Não desative validação TLS. |
| Respostas faladas | Ative para ouvir o Hermes. |
| Lembrar sessão | Opcional. Guarda um cookie local de acesso do app, não a senha. Esse cookie pode autorizar outros apps permitidos à mesma conta; proteja o aparelho. |

Salve e conecte. O endereço precisa estar acessível **pelo Moto**, com hostname
compatível com o certificado. Wi-Fi e Tailscale são rotas; não troque de conta
Tailscale nem altere SSH para configurar o app. Não copie cookies do navegador.

### Seu Umbrel usa HTTP? Use o Tailscale já existente

Ative/confira a conexão em **Painel → VPN / Tailscale**, na sua conta atual.
Na lista de dispositivos da sua Tailscale, copie o **IP do Umbrel**,
mantenha a porta pública do app Hermes e
use `http://IP:porta`. Por exemplo, um endereço de navegador como
`http://umbrel.local:18790/chat?profile=default` vira
`http://100.64.0.10:18790` no campo URL e `default` no campo Perfil, substituindo
o IP de exemplo pelo seu. Não inclua `/chat` nem `?profile=...` na URL.

Você pode usar esse mesmo endereço em casa ou conectado ao Wi-Fi de um hotspot,
desde que Moto e Umbrel tenham internet e acesso pela Tailscale. A senha Umbrel
continua sendo pedida; não é necessário configurar HTTPS no servidor nem mexer
no host do Umbrel. Em HTTP, o campo CA fica vazio.

O cliente verifica o daemon local e o peer e prende os sockets HTTP/WS à
interface Tailscale. Se a VPN parar, ele falha sem tentar a rede comum.
HTTP em IP da LAN, hostname `.local`, nome DNS ou IP público não é aceito.
Para HTTPS, a validação do certificado continua normal.

### Se você não usa 2FA

Digite **somente sua senha Umbrel** no formulário do telefone. O app completa
o login e a autorização de entrada do Hermes. Não precisa ativar 2FA.

### Se você usa 2FA

Depois da senha, se o servidor pedir, aparece o campo de código. Digite o
código atual do seu autenticador. Um código vencido pode ser tentado novamente;
isso não muda a configuração de segurança da conta.

Senhas e códigos ficam fora dos argumentos do terminal e dos logs. Ao sair do
fluxo de login, a senha retida em memória é descartada. Os arquivos privados
do telefone têm permissões restritas; não são um cofre criptografado.

## 5. Faça a primeira conversa

Para abrir em silêncio e esperar **“Olá Hermes”**, deixe **Começar a conversa ao
abrir** desmarcado. Depois da ativação, converse sem repetir a frase a cada
pergunta. Sem fala, ele permanece quieto na escuta. O cliente verifica cada
candidato de fala localmente com Silero antes de enviá-lo à Groq; o runtime,
`moto-vad` e o modelo precisam estar na mesma instalação atualizada.
Para a ativação atual, instale também o `moto-wake` correspondente e o modelo
multilíngue `ggml-base-q5_1.bin`; apenas o modelo tiny antigo não atende ao novo
runtime. O build e os destinos estão no [guia técnico](hermes-setup.md#prepare-a-userspace-installation).

Como alternativa explícita, para começar assim que abrir o bichinho, marque **Começar a conversa ao abrir**
em **Configurar**. Ao abrir, ele conecta e diz **“Olá! Estou ouvindo.”**; espere a
confirmação e faça a pergunta. A partir daí as falas seguem para a Groq e para
seu Hermes. Essa opção é explícita e vem desmarcada em configurações antigas.
Ela inicia a conversa pela abertura do app; não significa que a detecção local
de “Olá Hermes” foi corrigida. Com a opção desmarcada, siga a ativação abaixo.

1. Com o rosto conectado, diga **“Olá Hermes”** sozinho.
2. Espere **“Olá! Estou ouvindo.”**. A frase de ativação inteira é descartada;
   faça o pedido depois dessa confirmação.
3. Diga uma pergunta simples, por exemplo: **“Quanto é dois mais dois?”**.
   Pare de falar; após cerca de 700 ms de silêncio detectado, o app transcreve,
   consulta o agente e fala a resposta.
4. Faça outra pergunta quando ele voltar a ouvir. Não é preciso repetir
   “Olá Hermes” a cada turno.
5. Diga **“Nova conversa”** como uma fala completa. Isso cria um contexto novo
   no mesmo perfil. A conversa anterior permanece no servidor.
6. Diga **“Voltar ao terminal”** para fechar. Abra novamente para conferir que
   a conversa atual foi mantida e o terminal continua disponível.

| Você diz | Resultado |
| --- | --- |
| “Olá Hermes” | Ativa a conversa, a partir da espera local. |
| “Nova conversa” / “Hermes, nova conversa” | Troca o contexto atual depois da confirmação do servidor. |
| “Voltar a dormir” | Volta a esperar ativação local. |
| “Fechar aplicativo” / “Voltar ao terminal” | Fecha o app e encerra seus processos de áudio. |

O app usa uma conversa própria do Moto, diferente do Telegram. Fechar e reabrir
mantém essa conversa; **Nova conversa** troca o ID, preservando perfil e chats
antigos. A troca é bloqueada se houver uma tarefa em andamento ou resultado
incerto. Ela não apaga a memória permanente do perfil nem muda suas ferramentas.

A captura pausa durante transcrição, processamento e resposta falada. Aguarde
o rosto voltar a ouvir; interrupção por voz durante a reprodução ainda não foi
validada. Comandos falados após ativação também dependem da transcrição Groq.
O **×** continua disponível se a rede falhar. Apagar a tela interrompe a escuta;
isso só apaga a luz de fundo, não suspende nem bloqueia o sistema.

Apagar a tela pausa microfone, reprodução e animação, mas preserva a conexão
que recebe uma tarefa em andamento. Ao acender, o rosto volta ao estado atual.
Uma resposta concluída com a tela apagada fica guardada; use **··· → Ouvir
última resposta** para reproduzi-la, sem reenviar a pergunta ao agente.

## 6. Se algo não funcionar

| Sintoma | Próximo passo |
| --- | --- |
| A sessão existe, mas fica vazia ao dizer “Olá Hermes” | Espere a confirmação falada. A sessão é criada/retomada ao conectar; isso ainda não prova que a ativação aceitou sua voz. Consulte o diagnóstico local. |
| Falta componente/modelo | Siga o build/instalação completo; o app não envia áudio de espera à nuvem como alternativa. |
| Erro de certificado | Confira hostname, data/hora, CA e origens do app/login. Preserve a verificação TLS. |
| Login funciona no navegador, mas o app recusa | Confira conta, URL e contrato da versão Umbrel. Não exporte cookies nem abra porta interna. |
| Ouve a ativação, mas falha ao transcrever | Confira a chave Groq deste Moto, internet e quota. Grave uma nova fala; não há reenvio automático. |
| Texto funciona, voz não | Peça ao próprio Hermes para verificar Edge, voz e dependências no perfil combinado. Confira volume/saída nativa no Moto. |
| Microfone ocupado | Encerre o ditado/gravação anterior. Os dois recursos compartilham a posse da captura. |
| Resultado da tarefa desconhecido | Confira a conversa no Hermes antes de usar “Já conferi a tarefa”. Reconectar não significa desfazer ações já aceitas. |

Veja [diagnóstico detalhado](hermes-setup.md#disconnects-and-troubleshooting).
Não publique chave Groq, senha, cookie, gravações nem logs pessoais em issues.
O USB é a manutenção do aparelho; a conversa normal usa a rede do Moto.

Conclua a aceitação com sua voz e ruído ambiente: ativação, tempo de resposta,
fala audível, escuta após resposta, novo contexto, saída do app, terminal
preservado e observação de calor/autonomia. Teste automatizado não substitui isso.

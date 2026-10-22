# Moto G4 Linux

Um Linux nativo para dar uma segunda vida ao Moto G4 Plus: teclado de toque,
abas SSH, Wi-Fi salvo, Tailscale, áudio e ditado. O protótipo liga e desliga sem
PC e usa Alpine, Xorg, xterm/tmux e uma interface Python/Tk.

**Estado:** código experimental, validado numa unidade XT1640 / athene P2A,
2 GB / 32 GB. Não há instalador universal nem imagem pública pronta. O kernel é
3.10.108; suspensão, bloqueio de tela, fones/BT/modem e outros modelos continuam
pendentes. [Matriz completa](docs/status.md).

## Instale com seu agente

Abra o repositório no Codex, Claude Code ou agente local e envie:

> Quero instalar o Moto G4 Linux no celular conectado por USB. Leia AGENTS.md
> e docs/agent-installation.md. Inspecione meu aparelho e computador, confirme a
> compatibilidade, prepare backups privados verificados e faça o build. Antes
> de desbloquear, formatar ou gravar, mostre o plano exato e aguarde minha
> autorização. Use minhas próprias chaves e firmware, sem copiar outra identidade.

O [guia para agentes](docs/agent-installation.md) organiza as fases e os critérios
para avançar. A pessoa ainda aceita os avisos físicos, entra nas próprias contas
e informa segredos diretamente nos formulários.

Depois: Wi-Fi pelo painel, cadastro Tailscale por QR e favoritos SSH com senha
opcional. O microfone transcreve com sua chave Groq e insere na aba sem Enter.
[Guia de uso](docs/user-guide.md).

## App Hermes opcional

A nova prévia abre um bichinho em tela cheia: rosto animado, ativação local por
“Olá Hermes”, conversa por voz sem apertar botão e retorno ao terminal ao fechar.
“Nova conversa” inicia um contexto novo no mesmo perfil. Usa Rust, Groq para
transcrever as falas após ativação e Edge no próprio Hermes para responder.
O login aceita senha Umbrel sem 2FA ou pede código quando a conta exige.

A tela e o fluxo passam por testes isolados; o wake word ainda precisa de
aceitação física de precisão, velocidade e aquecimento no Moto. O painel antigo foi substituído no Moto de referência; falta configurar a
conexão e validar a conversa real. Veja [setup e limites](docs/hermes-setup.md)
e [pesquisa](docs/hermes-assistant.md). O próprio Hermes prepara a parte do
servidor com [estas instruções](docs/hermes-server-agent.md), dentro de seu app.
Nunca acesse ou administre o host do Umbrel para essa integração.

## Explore

[Documentação](docs/README.md) · [Instalação](docs/installation.md) ·
[Build](docs/building.md) · [Arquitetura](docs/architecture.md) ·
[Diagnóstico](docs/troubleshooting.md) · [Contribuir](CONTRIBUTING.md) ·
[Créditos](CREDITS.md) · [Wiki](https://github.com/holiveiraa/moto-g4-linux/wiki).

Código próprio, documentação e arte: MIT, com exceções de kernel/lk2nd em
[LICENSES/README.md](LICENSES/README.md). Firmware, chaves e dados particulares
não são distribuídos. [README completo em inglês](README.md).

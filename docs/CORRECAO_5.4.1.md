# QuestFlow Studio 5.4.1 — correção de instância fantasma

## Problema corrigido
Após fechar a janela do Chrome, o processo do Chrome podia permanecer vivo em segundo plano. O runtime 5.4.0 usava a condição `process.poll() is None OR heartbeat recente`, apesar de o próprio comentário definir o heartbeat como fonte autoritativa de vida da interface. Com isso, `pythonw.exe` permanecia ativo, segurava o lock `questflow_instance.lock` e a próxima abertura exibia falsamente que o QuestFlow já estava aberto.

## Correção
- heartbeat da interface passou a ser a fonte autoritativa após a inicialização;
- timeout de 12 s + janela de confirmação de 6 s protege contra suspensão/retorno do notebook;
- se a interface realmente desapareceu, o motor local, Cloud Sync e lock são encerrados mesmo que o Chrome deixe processo de fundo ativo;
- incluído `RECUPERAR_QUESTFLOW.bat` para encerrar com segurança apenas uma instância órfã desta instalação;
- instruções Turso alteradas para `turso db create questflow`, compatível com organizações sem `tursodb` habilitado.

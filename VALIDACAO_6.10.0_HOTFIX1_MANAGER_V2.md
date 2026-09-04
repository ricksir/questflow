# Validação — QuestFlow 6.10.0 HOTFIX1 Manager V2

## Correção principal
O processo de atualização foi movido para um PowerShell externo em `%LOCALAPPDATA%\QFS\manager`, evitando que o Manager atualize a própria árvore enquanto está executando nela. A nova janela mostra progresso periódico e mantém log em `%LOCALAPPDATA%\QFS\logs`.

## Testes executados
- 22 testes focados em hardening, backup/restauração, Mobile Professional UX, Study Session e Manager V2: aprovados.
- Simulação real de atualização 6.9.9 -> 6.10.0 usando `release_tools.py update`: aprovada.
- Na simulação, um banco SQLite com marcador de persistência foi preservado, `PRAGMA quick_check` retornou `ok`, `RECOVERY_GUARD.json` permaneceu intacto, Manager 2.0.0 foi instalado e o atualizador externo ficou presente após a atualização.

## Observação
A suíte completa foi iniciada neste ambiente, mas ultrapassou o limite operacional disponível. Por isso, este hotfix não declara uma nova execução completa de toda a suíte; a validação desta correção é baseada nos testes focados acima e na simulação de atualização real.

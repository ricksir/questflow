# QuestFlow Mobile API v1 — Studio 6.9.5 / Mobile 0.2.1

Contrato preservado: `questflow.mobile.v1`.

## Ciclo do aparelho

A rota existente `DELETE /api/v1/mobile/devices/{device_id}` continua encerrando as sessões do próprio aparelho. A mudança da 6.9.5 é de semântica e experiência: a ação é apresentada ao usuário como **Desconectar**, não “Revogar”.

O Studio mantém o registro do aparelho e o histórico. Um novo pareamento com o mesmo `device_id` reativa o mesmo registro. O cliente Mobile 0.2.1 persiste esse identificador de instalação fora da sessão, evitando duplicatas após desconectar/conectar novamente.

No Studio, **Remover da lista** é uma operação administrativa local que apenas oculta um aparelho já desconectado; não é uma nova rota da API Mobile e não apaga eventos de aprendizagem.

## Compatibilidade

O schema lógico da API permanece versão 1 e o contrato permanece `questflow.mobile.v1`. O alias técnico de “revoke” é mantido apenas internamente para compatibilidade com a 6.9.4.

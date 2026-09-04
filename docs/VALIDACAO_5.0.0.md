# Validação QuestFlow Studio 5.0.0

## Escopo

Validação da nova interface enterprise e regressão do núcleo funcional existente.

## Resultados

- 107 testes automatizados: aprovados;
- compilação de módulos Python: aprovada;
- sintaxe do JavaScript: aprovada;
- diagnóstico funcional: aprovado;
- versionamento entre `VERSION.txt` e `APP_VERSION`: consistente;
- ponte Python/JavaScript: testada com banco temporário;
- interface clássica: preservada.

## Testes específicos da interface

- presença de CSS Grid e Flexbox;
- Container Queries e contextos de contenção;
- tipografia e espaçamento com `clamp()`;
- mais de 80 tokens de design centralizados;
- tema por sistema e alternância manual;
- estados hover, focus, active, disabled, loading, erro e vazio;
- landmarks, ARIA, skip link e modal acessível;
- virtualização da lista de questões;
- `content-visibility` e lazy loading;
- editores estruturados de enunciado, alternativas e explicação;
- fallback para interface clássica.

## Limitações do ambiente de construção

O ambiente Linux usado para empacotar não possui `pywebview`, `selenium` e `pymupdf4llm`. O instalador do Windows inclui esses pacotes no `requirements.txt`. O diagnóstico local confirmou o fallback clássico e validou estaticamente a interface web; a abertura real do renderizador incorporado deve ser confirmada no Windows após a instalação.

## Arquivos de evidência

- `RESULTADO_TESTES_5.0.0.txt`;
- `RESULTADO_COMPILACAO_5.0.0.txt`;
- `RESULTADO_DIAGNOSTICO_5.0.0.txt`.

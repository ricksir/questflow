# Validação QuestFlow Studio 2.1.7

## Objetivo
Validar a releitura individual de questões, os novos modos de organização da tela e a exclusão definitiva da base.

## Testes realizados

1. **Compilação Python**
   - `app.py` e todos os módulos de `core` compilados sem erros.

2. **Diagnóstico local**
   - dependências, taxonomia, banco, Telegram e versão validados;
   - novos métodos de releitura, layout e exclusão identificados.

3. **PDF textual do Estratégia**
   - arquivo `tecinformacao1.pdf`;
   - 24 questões e 24 gabaritos extraídos;
   - imagens das questões 12 e 16 recortadas;
   - caminho completo do PDF gravado na fonte da questão.

4. **PDF no formato QConcursos**
   - arquivo `auditoria8.pdf`;
   - 5 questões e 5 gabaritos extraídos;
   - caminho completo do PDF gravado.

5. **Releitura individual**
   - questão localizada novamente pelo código, número ou similaridade do enunciado;
   - conteúdo atualizado no mesmo registro do banco;
   - classificação e imagem manuais preservadas;
   - questão marcada como pendente para nova conferência.

6. **Tela de revisão**
   - divisão horizontal e vertical;
   - troca entre lista e editor;
   - modos só lista, só editor e duas janelas;
   - divisor arrastável;
   - seleção integral de campos por Ctrl+A.

7. **Exclusão**
   - remoção da questão com cascata para estado de estudo, entregas e tentativas do Telegram.

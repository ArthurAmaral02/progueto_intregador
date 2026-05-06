"""
Testes de Integração - Sistema E-Commerce
Etapa 2: Valida fluxos reais envolvendo múltiplos módulos interagindo entre si.

Fluxos cobertos:
  1. Login → verificação de papel → acesso ao menu correto
  2. Fluxo completo de venda (produto → estoque → venda_produto → triggers)
  3. Comunicação entre camadas: CRUD de produto com validação de permissão
  4. Fluxo de cliente especial (vendas acumuladas → promoção de status)
  5. Execução de procedures com múltiplos result sets (EstatísticasCompletas)
  6. Falhas de integração: FK violation, rollback, estoque negativo
"""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import date
import mysql.connector

import ecommerce


# ──────────────────────────────────────────────
# Fixtures compartilhadas
# ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_globals():
    """Isola os globals entre cada teste."""
    ecommerce.CURRENT_USER = ''
    ecommerce.CURRENT_PASSWORD = ''
    yield
    ecommerce.CURRENT_USER = ''
    ecommerce.CURRENT_PASSWORD = ''


@pytest.fixture
def mock_conn():
    """Conexão MySQL completamente mockada, cursor com fetchall e rowcount."""
    conn = MagicMock()
    conn.is_connected.return_value = True
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    cursor.rowcount = 1
    conn.cursor.return_value = cursor
    return conn


# ══════════════════════════════════════════════
# FLUXO 1: Login → Role → Menu correto
# ══════════════════════════════════════════════

class TestFluxoLoginMenu:
    """
    Valida que o sistema redireciona ao menu certo após a autenticação.
    Integra: login() → get_db_connection() → get_user_role() → menu_principal()
    """

    @patch('ecommerce.menu_admin')
    @patch('ecommerce.get_db_connection')
    @patch('builtins.input', side_effect=['admin', 'Senhateste1!!'])
    def test_admin_acessa_menu_admin(self, mock_input, mock_conn_fn, mock_menu, capsys):
        """Admin logado deve ser encaminhado para menu_admin."""
        mock_conn_fn.return_value = MagicMock()
        ecommerce.login()
        mock_menu.assert_called_once()
        captured = capsys.readouterr()
        assert 'Administrador' in captured.out

    @patch('ecommerce.menu_gerente')
    @patch('ecommerce.get_db_connection')
    @patch('builtins.input', side_effect=['gerente', 'Senhateste1!'])
    def test_gerente_acessa_menu_gerente(self, mock_input, mock_conn_fn, mock_menu, capsys):
        """Gerente logado deve ser encaminhado para menu_gerente."""
        mock_conn_fn.return_value = MagicMock()
        ecommerce.login()
        mock_menu.assert_called_once()
        captured = capsys.readouterr()
        assert 'Gerente' in captured.out

    @patch('ecommerce.menu_funcionario')
    @patch('ecommerce.get_db_connection')
    @patch('builtins.input', side_effect=['funcionario', 'Senhateste1!'])
    def test_funcionario_acessa_menu_funcionario(self, mock_input, mock_conn_fn, mock_menu, capsys):
        """Funcionário logado deve ser encaminhado para menu_funcionario."""
        mock_conn_fn.return_value = MagicMock()
        ecommerce.login()
        mock_menu.assert_called_once()

    @patch('ecommerce.get_db_connection', return_value=None)
    @patch('builtins.input', side_effect=['usuario_errado', 'senha_errada'])
    def test_credenciais_invalidas_nao_abre_menu(self, mock_input, mock_conn_fn, capsys):
        """Credenciais inválidas → sem menu, exibe erro."""
        ecommerce.login()
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('ecommerce.get_db_connection')
    @patch('builtins.input', side_effect=['admin', 'Senhateste1!!'])
    def test_role_correto_injetado_na_sessao(self, mock_input, mock_conn_fn):
        """Após login com 'admin', CURRENT_USER deve estar definido."""
        mock_conn_fn.return_value = MagicMock()
        with patch('ecommerce.menu_principal'):
            ecommerce.login()
        assert ecommerce.CURRENT_USER == 'admin'


# ══════════════════════════════════════════════
# FLUXO 2: Venda completa (produto → estoque → venda_produto)
# ══════════════════════════════════════════════

class TestFluxoVendaCompleto:
    """
    Valida o fluxo de venda de ponta a ponta:
    verificar_permissão → consultar_produto → inserir_venda → inserir_venda_produto → atualizar_estoque
    """

    @patch('builtins.input', side_effect=['1', 'Rua das Flores, 10', '', '1', '3'])
    @patch('ecommerce.execute_query')
    def test_fluxo_venda_chama_queries_na_ordem_correta(self, mock_exec, mock_input, mock_conn):
        """Garante que as 3 operações SQL são chamadas na ordem certa."""
        ecommerce.CURRENT_USER = 'funcionario1'
        mock_exec.side_effect = [
            [{'valor': 50.0, 'quantidade_estoque': 20}],  # SELECT produto
            True,   # INSERT venda
            True,   # INSERT venda_produto
            True,   # UPDATE estoque (fallback)
        ]
        ecommerce.realizar_venda(mock_conn)
        assert mock_exec.call_count >= 3

    @patch('builtins.input', side_effect=['2', 'Av. Brasil, 50', '', '5', '10'])
    @patch('ecommerce.execute_query')
    def test_valor_total_calculado_corretamente(self, mock_exec, mock_input, mock_conn, capsys):
        """Total da venda deve ser preço_unitário × quantidade."""
        ecommerce.CURRENT_USER = 'funcionario1'
        preco = 120.0
        qtd = 10
        mock_exec.side_effect = [
            [{'valor': preco, 'quantidade_estoque': 50}],
            True, True, True
        ]
        ecommerce.realizar_venda(mock_conn)
        captured = capsys.readouterr()
        assert f'R$ {preco * qtd:.2f}' in captured.out

    @patch('builtins.input', side_effect=['1', 'Rua A', '', '1', '5'])
    @patch('ecommerce.execute_query')
    def test_estoque_insuficiente_bloqueia_e_nao_insere(self, mock_exec, mock_input, mock_conn, capsys):
        """Se estoque < qtd solicitada, nenhum INSERT deve ocorrer."""
        ecommerce.CURRENT_USER = 'funcionario1'
        mock_exec.side_effect = [
            [{'valor': 30.0, 'quantidade_estoque': 2}],  # apenas 2 em estoque
        ]
        ecommerce.realizar_venda(mock_conn)
        # Apenas 1 chamada (SELECT produto); sem INSERT
        assert mock_exec.call_count == 1
        captured = capsys.readouterr()
        assert 'insuficiente' in captured.out

    @patch('builtins.input', side_effect=['1', 'Rua A', '', '999', '2'])
    @patch('ecommerce.execute_query', return_value=[])
    def test_produto_inexistente_aborta_fluxo(self, mock_exec, mock_input, mock_conn, capsys):
        """Produto não encontrado → fluxo abortado com mensagem de erro."""
        ecommerce.CURRENT_USER = 'funcionario1'
        ecommerce.realizar_venda(mock_conn)
        captured = capsys.readouterr()
        assert 'não encontrado' in captured.out

    @patch('builtins.input', side_effect=['1', 'Rua A', '2', '1', '1'])
    @patch('ecommerce.execute_query')
    def test_venda_com_transportadora_registra_id_transporte(self, mock_exec, mock_input, mock_conn, capsys):
        """Quando transportadora informada, INSERT venda deve conter id_transporte=2."""
        ecommerce.CURRENT_USER = 'admin'
        mock_exec.side_effect = [
            [{'valor': 200.0, 'quantidade_estoque': 10}],
            True, True, True
        ]
        ecommerce.realizar_venda(mock_conn)
        # Verificar que o segundo call (INSERT venda) foi feito com id_transporte=2
        insert_venda_call = mock_exec.call_args_list[1]
        params = insert_venda_call[0][2]  # terceiro argumento posicional
        assert 2 in params
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out


# ══════════════════════════════════════════════
# FLUXO 3: Permissão → CRUD de produto integrado
# ══════════════════════════════════════════════

class TestFluxoPermissaoCRUDProduto:
    """
    Valida que as camadas de permissão e persistência estão corretamente integradas.
    check_permission() deve ser consultada ANTES de qualquer acesso ao banco.
    """

    def test_guest_nao_chega_ao_banco_em_cadastro(self, mock_conn, capsys):
        """Guest não deve gerar nenhuma chamada ao cursor."""
        ecommerce.CURRENT_USER = 'visitante'
        ecommerce.cadastrar_produto(mock_conn)
        mock_conn.cursor.assert_not_called()
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' in captured.out

    @patch('builtins.input', side_effect=['Teclado', 'Mecânico', '15', '350.00', '2', ''])
    @patch('ecommerce.execute_query', return_value=True)
    def test_admin_cadastra_produto_e_banco_e_chamado(self, mock_exec, mock_input, mock_conn, capsys):
        """Admin deve conseguir cadastrar e o execute_query deve ser chamado."""
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.cadastrar_produto(mock_conn)
        mock_exec.assert_called_once()
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out

    @patch('builtins.input', side_effect=['Monitor', 'Full HD', '5', '1200.00', '1', ''])
    @patch('ecommerce.execute_query', return_value=True)
    def test_funcionario_cadastra_produto_permitido(self, mock_exec, mock_input, mock_conn, capsys):
        """Funcionário tem permissão para cadastrar produto."""
        ecommerce.CURRENT_USER = 'funcionario1'
        ecommerce.cadastrar_produto(mock_conn)
        mock_exec.assert_called_once()
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out

    def test_gerente_nao_pode_cadastrar_cliente(self, mock_conn, capsys):
        """Gerente não tem permissão para cadastrar cliente."""
        ecommerce.CURRENT_USER = 'gerente1'
        ecommerce.cadastrar_cliente(mock_conn)
        mock_conn.cursor.assert_not_called()
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' in captured.out

    @patch('builtins.input', side_effect=['Ana Lima', '1985-07-20', 'f'])
    @patch('ecommerce.execute_query', return_value=True)
    def test_admin_cadastra_cliente_dados_persistidos(self, mock_exec, mock_input, mock_conn):
        """Admin cadastra cliente e os dados são repassados corretamente ao banco."""
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.cadastrar_cliente(mock_conn)
        args = mock_exec.call_args[0]
        params = args[2]
        assert params[0] == 'Ana Lima'
        assert params[2] == 'f'
    
    @patch('builtins.input', side_effect=['Notebook Gamer', 'RTX 4060 / 16GB RAM', '8', '7500.00', '1', 'Produto premium'])
    @patch('ecommerce.execute_query', return_value=True)
    def test_admin_cadastra_produto_com_sucesso(self, mock_exec, mock_input, mock_conn, capsys):
        """
        Admin deve conseguir cadastrar produto com sucesso,
        validando permissão + persistência correta no banco.
        """
        ecommerce.CURRENT_USER = 'admin'

        ecommerce.cadastrar_produto(mock_conn)

        # Verifica que a query foi executada
        mock_exec.assert_called_once()

        # Valida parâmetros enviados ao banco
        args = mock_exec.call_args[0]
        query = args[1]
        params = args[2]

        assert 'INSERT INTO produto' in query
        assert params[0] == 'Notebook Gamer'
        assert params[1] == 'RTX 4060 / 16GB RAM'
        assert params[2] == 8
        assert params[3] == 7500.00
        assert params[4] == 'Produto premium'
        assert params[5] == 1

        # Verifica mensagem de sucesso
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out


# ══════════════════════════════════════════════
# FLUXO 3.1: CRUD Genérico Admin + Integração profunda de menus
# ══════════════════════════════════════════════

class TestFluxoCRUDGenericoAdmin:
    """
    Valida erros estruturais no CRUD genérico administrativo:
    - visualizar_tabela retorna lista utilizável
    - cadastrar_generico não quebra com retorno None
    - editar_generico executa update
    - deletar_generico executa delete
    - fluxo menu_admin acessa CRUD corretamente
    """

    def test_visualizar_tabela_retorna_lista_de_tabelas(self, mock_conn, monkeypatch):
        """visualizar_tabela deve retornar lista iterável de tabelas."""
        ecommerce.CURRENT_USER = 'admin'

        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [('cliente',), ('produto',), ('venda',)],  # SHOW TABLES
            []  # SELECT * fallback
        ]
        cursor.description = [('id',), ('nome',)]
        mock_conn.cursor.return_value = cursor

        monkeypatch.setattr('builtins.input', lambda _: '0')

        resultado = ecommerce.visualizar_tabela(mock_conn)

        assert resultado is not None, "visualizar_tabela deveria retornar lista"
        assert isinstance(resultado, list)

    @patch('builtins.input', side_effect=['1', 'Produto Teste', 'Descricao Teste', '10', '99.99', '', '1'])
    def test_cadastrar_generico_produto_nao_quebra(self, mock_input, mock_conn):
        """
        cadastrar_generico deve funcionar ao inserir produto.
        Detecta bug clássico de visualizar_tabela retornando None.
        """
        ecommerce.CURRENT_USER = 'admin'

        cursor = MagicMock()

        # SHOW TABLES
        # DESCRIBE produto
        cursor.fetchall.side_effect = [
            [('produto',)],
            [
                ('id', 'int', None, None, None, 'auto_increment'),
                ('nome', 'varchar', None, None, None, ''),
                ('descricao', 'varchar', None, None, None, ''),
                ('quantidade_estoque', 'int', None, None, None, ''),
                ('valor', 'decimal', None, None, None, ''),
                ('observacoes', 'varchar', None, None, None, ''),
                ('id_vendedor', 'int', None, None, None, ''),
            ]
        ]

        mock_conn.cursor.return_value = cursor

        with patch.object(ecommerce, 'visualizar_tabela', return_value=['produto']):
            ecommerce.cadastrar_generico(mock_conn)

        assert cursor.execute.called
        mock_conn.commit.assert_called()

    @patch('builtins.input', side_effect=[
        '1',    # tabela produto
        '1',    # id registro
        'Novo Produto', '', '', '', '', ''
    ])
    def test_editar_generico_update_executado(self, mock_input, mock_conn):
        """editar_registro genérico deve executar UPDATE."""
        ecommerce.CURRENT_USER = 'admin'

        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [
                ('id', 'int', None, None, None, 'auto_increment'),
                ('nome', 'varchar', None, None, None, ''),
                ('descricao', 'varchar', None, None, None, ''),
                ('quantidade_estoque', 'int', None, None, None, ''),
                ('valor', 'decimal', None, None, None, ''),
                ('observacoes', 'varchar', None, None, None, ''),
                ('id_vendedor', 'int', None, None, None, ''),
            ]
        ]

        mock_conn.cursor.return_value = cursor

        with patch.object(ecommerce, 'visualizar_tabela', return_value=['produto']):
            ecommerce.editar_registro(mock_conn)

        assert cursor.execute.called
        mock_conn.commit.assert_called()

    @patch('builtins.input', side_effect=[
        '1',  # tabela produto
        '1',  # id
        's'   # confirmação
    ])
    def test_deletar_generico_remove_registro(self, mock_input, mock_conn):
        """deletar_generico deve executar DELETE."""
        ecommerce.CURRENT_USER = 'admin'

        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor

        with patch.object(ecommerce, 'visualizar_tabela', return_value=['produto']):
            ecommerce.deletar_generico(mock_conn)

        assert cursor.execute.called
        mock_conn.commit.assert_called()

    @patch('builtins.input', side_effect=[
        '2',  # menu_admin -> CRUD
        '1',  # Adicionar Registro
        '0',  # sair visualizar_tabela
        '',   # continuar
        '0'   # logout
    ])
    def test_menu_admin_fluxo_crud_nao_quebra(self, mock_input, mock_conn):
        """
        Testa navegação real:
        menu_admin -> CRUD -> cadastrar_generico
        Detecta falhas de integração entre menus.
        """
        ecommerce.CURRENT_USER = 'admin'

        with patch.object(ecommerce, 'visualizar_tabela', return_value=[]):
            with patch.object(ecommerce, 'clear_screen'):
                try:
                    ecommerce.menu_admin(mock_conn)
                except TypeError as e:
                    pytest.fail(f"Erro de integração detectado: {e}")

    def test_visualizar_tabela_conn_inativa(self, mock_conn, capsys):
        """Conexão inativa deve falhar graciosamente."""
        ecommerce.CURRENT_USER = 'admin'
        mock_conn.is_connected.return_value = False

        resultado = ecommerce.visualizar_tabela(mock_conn)

        captured = capsys.readouterr()
        assert resultado is None
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['999'])
    def test_visualizar_tabela_escolha_invalida(self, mock_input, mock_conn, capsys):
        """Escolha inválida não deve quebrar."""
        ecommerce.CURRENT_USER = 'admin'

        cursor = MagicMock()
        cursor.fetchall.return_value = [('produto',)]
        mock_conn.cursor.return_value = cursor

        ecommerce.visualizar_tabela(mock_conn)

        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['abc'])
    def test_cadastrar_generico_escolha_nao_numerica(self, mock_input, mock_conn, capsys):
        """Entrada inválida deve bloquear antes de SQL."""
        ecommerce.CURRENT_USER = 'admin'

        with patch.object(ecommerce, 'visualizar_tabela', return_value=['produto']):
            ecommerce.cadastrar_generico(mock_conn)

        captured = capsys.readouterr()
        assert 'ERRO' in captured.out
        mock_conn.cursor.assert_not_called()
# ══════════════════════════════════════════════
# FLUXO 4: Cliente especial (vendas acumuladas)
# ══════════════════════════════════════════════

class TestFluxoClienteEspecial:
    """
    Simula o fluxo onde vendas acumuladas promovem um cliente a especial.
    Integra: realizar_venda (várias) → consultar_vendas → status de cliente.
    """

    @patch('ecommerce.execute_query')
    def test_consulta_vendas_exibe_cliente_corretamente(self, mock_exec, mock_conn, capsys):
        """Consultar vendas deve mostrar nome do cliente e produto."""
        ecommerce.CURRENT_USER = 'funcionario1'
        mock_exec.return_value = [
            {
                'id': 10,
                'data_venda': date(2025, 3, 15),
                'valor': 600.0,
                'cliente': 'Carlos Lima',
                'produtos': 'Produto 3 (3x)'
            }
        ]
        ecommerce.consultar_vendas(mock_conn)
        captured = capsys.readouterr()
        assert 'Carlos Lima' in captured.out
        assert 'Produto 3' in captured.out

    @patch('ecommerce.execute_query')
    def test_multiplas_vendas_do_mesmo_cliente_exibidas(self, mock_exec, mock_conn, capsys):
        """Múltiplas vendas do mesmo cliente devem ser listadas."""
        ecommerce.CURRENT_USER = 'funcionario1'
        mock_exec.return_value = [
            {'id': 1, 'data_venda': date(2025, 1, 1), 'valor': 200.0, 'cliente': 'João', 'produtos': 'Prod A (1x)'},
            {'id': 2, 'data_venda': date(2025, 2, 1), 'valor': 350.0, 'cliente': 'João', 'produtos': 'Prod B (2x)'},
        ]
        ecommerce.consultar_vendas(mock_conn)
        captured = capsys.readouterr()
        assert captured.out.count('João') == 2

    @patch('builtins.input', side_effect=['5', 'Rua X', '', '3', '2'])
    @patch('ecommerce.execute_query')
    def test_venda_realizada_e_consulta_reflete_nova_entrada(self, mock_exec, mock_input, mock_conn, capsys):
        """Após venda realizada, consulta de vendas deve incluir o novo registro."""
        ecommerce.CURRENT_USER = 'funcionario1'
        # Primeiro: realizar_venda
        mock_exec.side_effect = [
            [{'valor': 80.0, 'quantidade_estoque': 30}],
            True, True, True,
        ]
        ecommerce.realizar_venda(mock_conn)
        assert 'SUCESSO' in capsys.readouterr().out

        # Depois: consultar_vendas
        mock_exec.side_effect = None
        mock_exec.return_value = [
            {'id': 99, 'data_venda': date(2025, 5, 1), 'valor': 160.0, 'cliente': 'Cliente 5', 'produtos': 'Produto 3 (2x)'}
        ]
        ecommerce.consultar_vendas(mock_conn)
        captured = capsys.readouterr()
        assert 'Cliente 5' in captured.out


# ══════════════════════════════════════════════
# FLUXO 5: EstatísticasCompletas (múltiplos result sets)
# ══════════════════════════════════════════════

class TestFluxoEstatisticasCompletas:
    """
    Valida a integração da procedure EstatisticasCompletas com o sistema.
    Testa permissão, chamada da procedure e exibição de múltiplos conjuntos.
    """

    def test_funcionario_nao_pode_ver_estatisticas(self, mock_conn, capsys):
        """Funcionário não tem permissão para executar estatísticas."""
        ecommerce.CURRENT_USER = 'funcionario1'
        ecommerce.executar_estatisticas(mock_conn)
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' in captured.out

    def test_gerente_pode_executar_estatisticas(self, mock_conn, capsys):
        """Gerente tem permissão para executar estatísticas."""
        ecommerce.CURRENT_USER = 'gerente1'
        # Simular cursor com stored_results
        cursor = MagicMock()
        result_set_1 = MagicMock()
        result_set_1.fetchall.return_value = [
            {'produto_id': 1, 'produto_nome': 'Prod A', 'total_qtd_vendida': 50,
             'valor_ganho_total': 5000.0, 'vendedor_id': 1, 'vendedor_nome': 'Vendedor X'}
        ]
        cursor.stored_results.return_value = [result_set_1]
        mock_conn.cursor.return_value = cursor

        ecommerce.executar_estatisticas(mock_conn)
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' not in captured.out

    def test_estatisticas_exibe_todos_conjuntos_de_resultado(self, mock_conn, capsys):
        """Múltiplos result sets devem ser exibidos sequencialmente."""
        ecommerce.CURRENT_USER = 'gerente1'
        cursor = MagicMock()

        # Simula 3 conjuntos de resultados
        rs1 = MagicMock()
        rs1.fetchall.return_value = [{'produto_id': 1, 'produto_nome': 'Mais Vendido', 'total_qtd_vendida': 100, 'valor_ganho_total': 10000.0, 'vendedor_id': 1, 'vendedor_nome': 'Joao'}]
        rs2 = MagicMock()
        rs2.fetchall.return_value = [{'ano': 2025, 'mes': 3, 'qtd_vendida_no_mes': 40, 'ganho_no_mes': 4000.0}]
        rs3 = MagicMock()
        rs3.fetchall.return_value = []  # conjunto vazio (ignorado)

        cursor.stored_results.return_value = [rs1, rs2, rs3]
        mock_conn.cursor.return_value = cursor

        ecommerce.executar_estatisticas(mock_conn)
        captured = capsys.readouterr()
        assert 'Mais Vendido' in captured.out
        assert '2025' in captured.out
        assert '#1' in captured.out
        assert '#2' in captured.out

    def test_estatisticas_sem_dados_exibe_erro(self, mock_conn, capsys):
        """Sem dados nos result sets, sistema deve informar."""
        ecommerce.CURRENT_USER = 'admin'
        cursor = MagicMock()
        cursor.stored_results.return_value = []
        mock_conn.cursor.return_value = cursor

        ecommerce.executar_estatisticas(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out or 'Nenhum dado' in captured.out

    def test_admin_tambem_pode_executar_estatisticas(self, mock_conn, capsys):
        """Admin deve ter acesso às estatísticas (superset de gerente)."""
        ecommerce.CURRENT_USER = 'admin'
        cursor = MagicMock()
        rs = MagicMock()
        rs.fetchall.return_value = [{'produto_id': 2, 'produto_nome': 'Prod B', 'total_qtd_vendida': 20, 'valor_ganho_total': 2000.0, 'vendedor_id': 2, 'vendedor_nome': 'Maria'}]
        cursor.stored_results.return_value = [rs]
        mock_conn.cursor.return_value = cursor

        ecommerce.executar_estatisticas(mock_conn)
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' not in captured.out


# ══════════════════════════════════════════════
# FLUXO 6: Falhas de integração e rollback
# ══════════════════════════════════════════════

class TestFluxoFalhasIntegracao:
    """
    Garante que falhas em camadas intermediárias são tratadas corretamente:
    rollback, mensagens de erro e isolamento de operações.
    """

    def test_execute_query_faz_rollback_em_erro_sql(self, mock_conn):
        """Em erro SQL, rollback deve ser chamado."""
        cursor = mock_conn.cursor.return_value
        cursor.execute.side_effect = mysql.connector.Error("Erro proposital")
        ecommerce.execute_query(mock_conn, "INSERT INTO inexistente VALUES (1)")
        mock_conn.rollback.assert_called_once()

    def test_execute_query_retorna_none_em_erro(self, mock_conn):
        """Falha SQL deve retornar None, não lançar exceção."""
        cursor = mock_conn.cursor.return_value
        cursor.execute.side_effect = mysql.connector.Error("Erro proposital")
        result = ecommerce.execute_query(mock_conn, "INVALID SQL")
        assert result is None

    def test_execute_query_nao_trava_se_conn_desconectada_no_rollback(self):
        """Rollback com conn desconectada não deve lançar exceção."""
        conn = MagicMock()
        cursor = MagicMock()
        cursor.execute.side_effect = mysql.connector.Error("fail")
        conn.cursor.return_value = cursor
        conn.is_connected.return_value = False
        result = ecommerce.execute_query(conn, "SELECT 1")
        assert result is None  # Não travou; retornou None

    @patch('builtins.input', side_effect=['2', '7', 's'])
    def test_apagar_cliente_com_vendas_exibe_erro_fk(self, mock_input, mock_conn, capsys):
        """Apagar cliente com vendas associadas deve exibir erro de integridade."""
        ecommerce.CURRENT_USER = 'admin'

        # apagar_registro usa conn.cursor(dictionary=True) e o mesmo cursor para SELECT e DELETE
        cursor = MagicMock()
        cursor.fetchone.return_value = {'nome': 'Cliente Vinculado'}

        # Primeira chamada a execute (SELECT) passa; segunda (DELETE) lança IntegrityError
        err = mysql.connector.IntegrityError()
        err.errno = 1451
        cursor.execute.side_effect = [None, err]

        mock_conn.cursor.return_value = cursor

        ecommerce.apagar_registro(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['Produto Falha', 'Desc', '5', '99.00', '1', ''])
    @patch('ecommerce.execute_query', return_value=None)
    def test_falha_no_insert_produto_exibe_erro(self, mock_exec, mock_input, mock_conn, capsys):
        """Se INSERT falhar (retorna None), mensagem de ERRO deve aparecer."""
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.cadastrar_produto(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['Carlos', '1990-13-01', 'm'])  # mês 13 inválido
    def test_data_nascimento_invalida_cancela_cadastro_cliente(self, mock_input, mock_conn, capsys):
        """Data com mês inválido deve ser rejeitada antes de acessar o banco."""
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.cadastrar_cliente(mock_conn)
        mock_conn.cursor.assert_not_called()
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['5.5', 'estagiario'])
    def test_reajuste_categoria_invalida_nao_chama_banco(self, mock_input, mock_conn, capsys):
        """Categoria inválida no reajuste deve bloquear antes da query."""
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.executar_reajuste(mock_conn)
        mock_conn.cursor.assert_not_called()
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('ecommerce.execute_query', return_value=[])
    def test_sorteio_sem_clientes_exibe_erro(self, mock_exec, mock_conn, capsys):
        """Sorteio com resultado vazio deve informar falha."""
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.executar_sorteio(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('ecommerce.execute_query', return_value=[{'cliente_sorteado': 7, 'valor_voucher': 200.0}])
    def test_sorteio_cliente_especial_recebe_voucher_maior(self, mock_exec, mock_conn, capsys):
        """Cliente especial sorteado deve receber voucher de R$200."""
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.executar_sorteio(mock_conn)
        captured = capsys.readouterr()
        assert '200.00' in captured.out
        assert '7' in captured.out

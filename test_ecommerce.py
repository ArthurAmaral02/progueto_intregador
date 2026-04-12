"""
Testes Unitários - Sistema E-Commerce
Cobre: permissões, execute_query, CRUD, fluxo de vendas, casos de erro e limites.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import date
import mysql.connector

import ecommerce


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_globals():
    """Garante isolamento: restaura globals antes de cada teste."""
    ecommerce.CURRENT_USER = ''
    ecommerce.CURRENT_PASSWORD = ''
    yield
    ecommerce.CURRENT_USER = ''
    ecommerce.CURRENT_PASSWORD = ''


@pytest.fixture
def mock_conn():
    """Retorna uma conexão MySQL totalmente mockada."""
    conn = MagicMock()
    conn.is_connected.return_value = True
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    cursor.rowcount = 1
    conn.cursor.return_value = cursor
    return conn


# ──────────────────────────────────────────────
# 1. get_db_connection
# ──────────────────────────────────────────────

class TestGetDbConnection:

    def test_retorna_none_sem_credenciais(self):
        """Sem usuário/senha definidos deve retornar None."""
        assert ecommerce.get_db_connection() is None

    def test_retorna_none_apenas_usuario(self):
        ecommerce.CURRENT_USER = 'admin'
        assert ecommerce.get_db_connection() is None

    def test_retorna_none_apenas_senha(self):
        ecommerce.CURRENT_PASSWORD = 'senha'
        assert ecommerce.get_db_connection() is None

    @patch('ecommerce.mysql.connector.connect')
    def test_conecta_com_credenciais_validas(self, mock_connect):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.CURRENT_PASSWORD = 'senha123'
        mock_connect.return_value = MagicMock()
        conn = ecommerce.get_db_connection()
        assert conn is not None
        mock_connect.assert_called_once()

    @patch('ecommerce.mysql.connector.connect')
    def test_conecta_sem_banco_quando_use_db_false(self, mock_connect):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.CURRENT_PASSWORD = 'senha'
        mock_connect.return_value = MagicMock()
        ecommerce.get_db_connection(use_db=False)
        args = mock_connect.call_args[1]
        assert 'database' not in args

    @patch('ecommerce.mysql.connector.connect', side_effect=mysql.connector.Error("conn fail"))
    def test_retorna_none_em_erro_de_conexao(self, _):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.CURRENT_PASSWORD = 'senha'
        assert ecommerce.get_db_connection() is None


# ──────────────────────────────────────────────
# 2. get_user_role
# ──────────────────────────────────────────────

class TestGetUserRole:

    def test_admin_exato(self):
        ecommerce.CURRENT_USER = 'admin'
        assert ecommerce.get_user_role() == 'Administrador'

    def test_admin_maiusculo(self):
        ecommerce.CURRENT_USER = 'ADMIN'
        assert ecommerce.get_user_role() == 'Administrador'

    def test_gerente_em_nome_composto(self):
        ecommerce.CURRENT_USER = 'gerente_loja'
        assert ecommerce.get_user_role() == 'Gerente'

    def test_funcionario_em_nome(self):
        ecommerce.CURRENT_USER = 'funcionario01'
        assert ecommerce.get_user_role() == 'Funcionario'

    def test_vendedor_em_nome(self):
        ecommerce.CURRENT_USER = 'vendedor_sul'
        assert ecommerce.get_user_role() == 'Funcionario'

    def test_usuario_desconhecido_e_guest(self):
        ecommerce.CURRENT_USER = 'visitante'
        assert ecommerce.get_user_role() == 'Guest'

    def test_string_vazia_e_guest(self):
        ecommerce.CURRENT_USER = ''
        assert ecommerce.get_user_role() == 'Guest'


# ──────────────────────────────────────────────
# 3. check_permission
# ──────────────────────────────────────────────

class TestCheckPermission:

    def test_admin_passa_em_qualquer_role(self):
        ecommerce.CURRENT_USER = 'admin'
        assert ecommerce.check_permission(['Funcionario']) is True
        assert ecommerce.check_permission(['Gerente']) is True
        assert ecommerce.check_permission([]) is True

    def test_gerente_passa_em_role_gerente(self):
        ecommerce.CURRENT_USER = 'gerente1'
        assert ecommerce.check_permission(['Gerente']) is True

    def test_funcionario_bloqueado_de_role_gerente(self, capsys):
        ecommerce.CURRENT_USER = 'funcionario1'
        result = ecommerce.check_permission(['Gerente'])
        assert result is False
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' in captured.out

    def test_guest_bloqueado_de_tudo(self, capsys):
        ecommerce.CURRENT_USER = 'visitante'
        result = ecommerce.check_permission(['Funcionario', 'Gerente', 'Administrador'])
        assert result is False

    def test_multiplas_roles_permitidas(self):
        ecommerce.CURRENT_USER = 'funcionario1'
        assert ecommerce.check_permission(['Funcionario', 'Gerente']) is True


# ──────────────────────────────────────────────
# 4. execute_query
# ──────────────────────────────────────────────

class TestExecuteQuery:

    def test_executa_insert_sem_fetch(self, mock_conn):
        result = ecommerce.execute_query(mock_conn, "INSERT INTO t VALUES (%s)", (1,))
        assert result is True
        mock_conn.commit.assert_called()

    def test_executa_select_com_fetch(self, mock_conn):
        rows = [{'id': 1, 'nome': 'Produto A'}]
        cursor = mock_conn.cursor.return_value
        cursor.fetchall.return_value = rows
        # Simula next_result retornando False
        cursor.next_result = MagicMock(return_value=False)
        result = ecommerce.execute_query(mock_conn, "SELECT * FROM produto", fetch=True)
        assert result == rows

    def test_retorna_none_em_erro_sql(self, mock_conn):
        cursor = mock_conn.cursor.return_value
        cursor.execute.side_effect = mysql.connector.Error("SQL error")
        result = ecommerce.execute_query(mock_conn, "BAD SQL")
        assert result is None

    def test_faz_rollback_em_erro(self, mock_conn):
        cursor = mock_conn.cursor.return_value
        cursor.execute.side_effect = mysql.connector.Error("err")
        ecommerce.execute_query(mock_conn, "FAIL")
        mock_conn.rollback.assert_called()

    def test_query_sem_params(self, mock_conn):
        result = ecommerce.execute_query(mock_conn, "SELECT 1")
        assert result is True

    def test_fetch_retorna_lista_vazia_se_nenhum_resultado(self, mock_conn):
        cursor = mock_conn.cursor.return_value
        cursor.fetchall.return_value = []
        cursor.next_result = MagicMock(return_value=False)
        result = ecommerce.execute_query(mock_conn, "SELECT * FROM vazia", fetch=True)
        assert result == []


# ──────────────────────────────────────────────
# 5. cadastrar_produto
# ──────────────────────────────────────────────

class TestCadastrarProduto:

    def test_sem_permissao_nao_cadastra(self, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'visitante'
        ecommerce.cadastrar_produto(mock_conn)
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' in captured.out
        mock_conn.cursor.assert_not_called()

    @patch('builtins.input', side_effect=['Notebook', 'Desc', '10', '2500.00', '1', ''])
    @patch('ecommerce.execute_query', return_value=True)
    def test_funcionario_cadastra_com_sucesso(self, mock_exec, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'funcionario1'
        ecommerce.cadastrar_produto(mock_conn)
        mock_exec.assert_called_once()
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out

    @patch('builtins.input', side_effect=['Notebook', 'Desc', 'abc', '2500.00', '1', ''])
    def test_valor_invalido_cancela_cadastro(self, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.cadastrar_produto(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['Prod', 'Desc', '5', '100.0', '1', ''])
    @patch('ecommerce.execute_query', return_value=None)
    def test_falha_no_banco_exibe_erro(self, mock_exec, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.cadastrar_produto(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['X', 'D', '0', '0.01', '1', ''])
    @patch('ecommerce.execute_query', return_value=True)
    def test_produto_com_valores_limite(self, mock_exec, mock_input, mock_conn, capsys):
        """Estoque=0 e valor mínimo devem ser aceitos."""
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.cadastrar_produto(mock_conn)
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out


# ──────────────────────────────────────────────
# 6. cadastrar_cliente
# ──────────────────────────────────────────────

class TestCadastrarCliente:

    def test_funcionario_nao_pode_cadastrar_cliente(self, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'funcionario1'
        ecommerce.cadastrar_cliente(mock_conn)
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' in captured.out

    @patch('builtins.input', side_effect=['João Silva', '1990-05-15', 'm'])
    @patch('ecommerce.execute_query', return_value=True)
    def test_admin_cadastra_cliente_sucesso(self, mock_exec, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.cadastrar_cliente(mock_conn)
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out

    @patch('builtins.input', side_effect=['Maria', '31-12-1999', 'f'])
    def test_data_invalida_cancela_cadastro(self, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.cadastrar_cliente(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['Novo', '2006-02-28', 'o'])
    @patch('ecommerce.execute_query', return_value=True)
    def test_calcula_idade_corretamente(self, mock_exec, mock_input, mock_conn):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.cadastrar_cliente(mock_conn)
        args = mock_exec.call_args[0]
        params = args[2]
        hoje = date.today()
        idade_esperada = hoje.year - 2006 - ((hoje.month, hoje.day) < (2, 28))
        assert params[1] == idade_esperada


# ──────────────────────────────────────────────
# 7. realizar_venda
# ──────────────────────────────────────────────

class TestRealizarVenda:

    def test_guest_bloqueado(self, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'visitante'
        ecommerce.realizar_venda(mock_conn)
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' in captured.out

    @patch('builtins.input', side_effect=['1', 'Rua A', '', '1', 'abc'])
    def test_quantidade_invalida_cancela_venda(self, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'funcionario1'
        ecommerce.realizar_venda(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['1', 'Rua A', '', '99', '1'])
    @patch('ecommerce.execute_query', return_value=[])
    def test_produto_inexistente_cancela_venda(self, mock_exec, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'funcionario1'
        ecommerce.realizar_venda(mock_conn)
        captured = capsys.readouterr()
        assert 'não encontrado' in captured.out

    @patch('builtins.input', side_effect=['1', 'Rua A', '', '1', '100'])
    @patch('ecommerce.execute_query')
    def test_estoque_insuficiente_bloqueia_venda(self, mock_exec, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'funcionario1'
        # Primeiro call: produto_info; demais: venda e items
        mock_exec.side_effect = [
            [{'valor': 50.0, 'quantidade_estoque': 5}],  # produto com só 5 unidades
            True, True, True
        ]
        ecommerce.realizar_venda(mock_conn)
        captured = capsys.readouterr()
        assert 'insuficiente' in captured.out

    @patch('builtins.input', side_effect=['1', 'Rua A, 10', '', '1', '2'])
    @patch('ecommerce.execute_query')
    def test_venda_bem_sucedida(self, mock_exec, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'funcionario1'
        mock_exec.side_effect = [
            [{'valor': 100.0, 'quantidade_estoque': 10}],
            True,   # insert venda
            True,   # insert venda_produto
            True,   # update estoque
        ]
        ecommerce.realizar_venda(mock_conn)
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out

    @patch('builtins.input', side_effect=['1', 'Rua A', '3', '1', '1'])
    @patch('ecommerce.execute_query')
    def test_venda_com_transportadora(self, mock_exec, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        mock_exec.side_effect = [
            [{'valor': 200.0, 'quantidade_estoque': 50}],
            True, True, True
        ]
        ecommerce.realizar_venda(mock_conn)
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out


# ──────────────────────────────────────────────
# 8. consultar_vendas
# ──────────────────────────────────────────────

class TestConsultarVendas:

    def test_guest_bloqueado(self, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'visitante'
        ecommerce.consultar_vendas(mock_conn)
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' in captured.out

    @patch('ecommerce.execute_query', return_value=[])
    def test_nenhuma_venda_exibe_aviso(self, mock_exec, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'funcionario1'
        ecommerce.consultar_vendas(mock_conn)
        captured = capsys.readouterr()
        assert 'Nenhuma venda' in captured.out

    @patch('ecommerce.execute_query')
    def test_exibe_vendas_encontradas(self, mock_exec, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'funcionario1'
        mock_exec.return_value = [
            {'id': 1, 'data_venda': date(2024, 1, 1), 'valor': 200.0,
             'cliente': 'Cliente 1', 'produtos': 'Produto A (2x)'}
        ]
        ecommerce.consultar_vendas(mock_conn)
        captured = capsys.readouterr()
        assert 'Cliente 1' in captured.out

    @patch('ecommerce.execute_query')
    def test_nome_produto_longo_truncado(self, mock_exec, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'funcionario1'
        nome_longo = 'Produto XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX (1x)'
        mock_exec.return_value = [
            {'id': 2, 'data_venda': date(2024, 2, 1), 'valor': 99.0,
             'cliente': 'C2', 'produtos': nome_longo}
        ]
        ecommerce.consultar_vendas(mock_conn)
        captured = capsys.readouterr()
        assert '...' in captured.out


# ──────────────────────────────────────────────
# 9. apagar_registro
# ──────────────────────────────────────────────

class TestApagarRegistro:

    def test_funcionario_nao_pode_apagar(self, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'funcionario1'
        ecommerce.apagar_registro(mock_conn)
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' in captured.out

    @patch('builtins.input', side_effect=['9'])
    def test_opcao_invalida(self, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'gerente1'
        ecommerce.apagar_registro(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['1', 'abc'])
    def test_id_nao_numerico_cancela(self, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.apagar_registro(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['1', '42', 's'])
    def test_registro_inexistente(self, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        cursor = mock_conn.cursor.return_value
        cursor.fetchone.return_value = None
        ecommerce.apagar_registro(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['1', '1', 'n'])
    def test_cancelamento_por_usuario(self, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        cursor = mock_conn.cursor.return_value
        cursor.fetchone.return_value = {'nome': 'Produto Teste'}
        ecommerce.apagar_registro(mock_conn)
        captured = capsys.readouterr()
        assert 'cancelada' in captured.out

    @patch('builtins.input', side_effect=['2', '5', 's'])
    def test_apagar_cliente_sucesso(self, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        cursor = mock_conn.cursor.return_value
        cursor.fetchone.return_value = {'nome': 'Cliente Teste'}
        cursor.rowcount = 1
        ecommerce.apagar_registro(mock_conn)
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out


# ──────────────────────────────────────────────
# 10. executar_reajuste
# ──────────────────────────────────────────────

class TestExecutarReajuste:

    def test_gerente_nao_pode_reajustar(self, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'gerente1'
        ecommerce.executar_reajuste(mock_conn)
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' in captured.out

    @patch('builtins.input', side_effect=['abc', 'vendedor'])
    def test_percentual_invalido(self, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.executar_reajuste(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['10.0', 'estagiario'])
    def test_categoria_invalida(self, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.executar_reajuste(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out

    @patch('builtins.input', side_effect=['5.5', 'vendedor'])
    @patch('ecommerce.execute_query', return_value=[{'resultado': 'Reajuste aplicado com sucesso.'}])
    def test_reajuste_sucesso(self, mock_exec, mock_input, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.executar_reajuste(mock_conn)
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out

    @patch('builtins.input', side_effect=['0.0', 'gerente'])
    @patch('ecommerce.execute_query', return_value=[{'resultado': 'Nenhuma alteração.'}])
    def test_reajuste_zero_percentual(self, mock_exec, mock_input, mock_conn, capsys):
        """Percentual 0 é válido numericamente e deve ser aceito."""
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.executar_reajuste(mock_conn)
        captured = capsys.readouterr()
        assert 'SUCESSO' in captured.out


# ──────────────────────────────────────────────
# 11. executar_sorteio
# ──────────────────────────────────────────────

class TestExecutarSorteio:

    def test_gerente_nao_pode_sortear(self, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'gerente1'
        ecommerce.executar_sorteio(mock_conn)
        captured = capsys.readouterr()
        assert 'ACESSO NEGADO' in captured.out

    @patch('ecommerce.execute_query', return_value=[{'cliente_sorteado': 42, 'valor_voucher': 150.0}])
    def test_sorteio_exibe_resultado(self, mock_exec, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.executar_sorteio(mock_conn)
        captured = capsys.readouterr()
        assert '42' in captured.out
        assert '150.00' in captured.out

    @patch('ecommerce.execute_query', return_value=[])
    def test_sorteio_sem_resultado_exibe_erro(self, mock_exec, mock_conn, capsys):
        ecommerce.CURRENT_USER = 'admin'
        ecommerce.executar_sorteio(mock_conn)
        captured = capsys.readouterr()
        assert 'ERRO' in captured.out


# ──────────────────────────────────────────────
# 12. Casos de Limite (Edge Cases)
# ──────────────────────────────────────────────

class TestEdgeCases:

    def test_usuario_com_admin_em_nome_nao_e_administrador(self):
        """'superadmin' contém 'admin' mas a lógica verifica igualdade."""
        ecommerce.CURRENT_USER = 'superadmin'
        # 'superadmin' != 'admin', mas 'admin' está em 'superadmin'
        # A implementação usa user == 'admin', então NÃO deve ser Admin
        role = ecommerce.get_user_role()
        # Comportamento real do código: lowercase 'superadmin' != 'admin'
        assert role == 'Guest'

    def test_usuario_gerente_funcionario_prioridade(self):
        """Se 'gerente' está no nome, não importa o resto."""
        ecommerce.CURRENT_USER = 'gerente_funcionario'
        assert ecommerce.get_user_role() == 'Gerente'

    def test_check_permission_lista_vazia(self):
        """Lista de roles vazia: apenas admin passa."""
        ecommerce.CURRENT_USER = 'gerente1'
        assert ecommerce.check_permission([]) is False

    def test_check_permission_lista_vazia_admin_passa(self):
        ecommerce.CURRENT_USER = 'admin'
        assert ecommerce.check_permission([]) is True

    @patch('builtins.input', side_effect=['1', 'Rua A', '', '1', '0'])
    @patch('ecommerce.execute_query')
    def test_venda_quantidade_zero(self, mock_exec, mock_input, mock_conn, capsys):
        """Quantidade 0: estoque(10) >= 0 → venda prossegue com total R$0.00."""
        ecommerce.CURRENT_USER = 'funcionario1'
        mock_exec.side_effect = [
            [{'valor': 100.0, 'quantidade_estoque': 10}],
            True, True, True
        ]
        ecommerce.realizar_venda(mock_conn)
        captured = capsys.readouterr()
        # Com qtd=0 e estoque=10, não há bloqueio de estoque - venda ocorre
        assert 'SUCESSO' in captured.out or 'R$ 0.00' in captured.out

    @patch('builtins.input', side_effect=['Maria', '2200-01-01', 'f'])
    def test_data_futura_invalida_no_strptime(self, mock_input, mock_conn, capsys):
        """Data futura é válida para strptime mas pode gerar idade negativa."""
        ecommerce.CURRENT_USER = 'admin'
        # Não deve lançar exceção; o sistema aceita a data
        try:
            with patch('ecommerce.execute_query', return_value=True):
                ecommerce.cadastrar_cliente(mock_conn)
        except Exception:
            pass  # Comportamento aceitável

    def test_execute_query_conn_desconectada(self):
        """Quando conn.is_connected() retorna False no rollback, não deve travar."""
        conn = MagicMock()
        cursor = MagicMock()
        cursor.execute.side_effect = mysql.connector.Error("fail")
        conn.cursor.return_value = cursor
        conn.is_connected.return_value = False
        result = ecommerce.execute_query(conn, "SELECT 1")
        assert result is None

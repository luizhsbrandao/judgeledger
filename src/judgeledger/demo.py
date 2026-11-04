"""Synthetic demo ledger: 44 judgments, 40 resolved, with fixed timestamps.

Every date is fixed here, so `build()` produces byte-identical files on every run. That is what
lets the test suite assert a stable report digest and keeps `jl demo` honest: the numbers in the
output come from a ledger anyone can regenerate and check by hand.
"""

from __future__ import annotations

from datetime import date, timedelta

from .model import Evidence
from .store import Ledger

ACTOR = "demo"
T0 = "2025-01-02T12:00:00Z"

# lead time in days, cycled to populate every horizon bucket
LEADS = (20, 45, 120, 400)

# (question, criteria, due, kind, value, outcome, tags)
ROWS: list[tuple[str, str, str, str, object, int | None, tuple[str, ...]]] = [
    (
        "Programa Alfa entrega o módulo 2 até o fim do trimestre",
        "Release notes assinadas e deploy em produção registrado no changelog",
        "2025-03-31",
        "interval",
        (0.60, 0.80),
        1,
        ("programa",),
    ),
    (
        "Indicador Beta fica abaixo de 4% na medição de abril",
        "Boletim mensal publicado pela equipe de medição com série revisada",
        "2025-04-30",
        "point",
        0.70,
        1,
        ("indicador",),
    ),
    (
        "Time Gama conclui a migração do banco até 15/05",
        "Janela de manutenção concluída sem rollback registrado",
        "2025-05-15",
        "interval",
        (0.55, 0.75),
        0,
        ("infra",),
    ),
    (
        "Fornecedor Delta renova o contrato sem reajuste acima de 10%",
        "Contrato assinado e publicado no portal de transparência",
        "2025-06-30",
        "interval",
        (0.45, 0.65),
        1,
        ("contrato",),
    ),
    (
        "Unidade Épsilon fica sem energia por mais de 4 horas no semestre",
        "Relatório de incidentes do datacenter, ocorrência classificada como P1",
        "2025-06-30",
        "point",
        0.65,
        0,
        ("infra",),
    ),
    (
        "Relatório Zeta é publicado antes de 20/07",
        "Documento indexado no repositório institucional com data de publicação",
        "2025-07-20",
        "interval",
        (0.70, 0.90),
        1,
        ("publicacao",),
    ),
    (
        "Projeto Eta passa na revisão externa sem ressalvas",
        "Parecer final do revisor externo, sem itens bloqueantes",
        "2025-08-29",
        "interval",
        (0.50, 0.70),
        1,
        ("revisao",),
    ),
    (
        "Taxa Teta fica acima de 12% no fechamento do trimestre",
        "Série oficial revisada publicada pela autoridade estatística",
        "2025-09-30",
        "point",
        0.40,
        0,
        ("indicador",),
    ),
    (
        "Equipe Iota tem rotatividade acima de 15% no ano",
        "Relatório anual de pessoal, desligamentos voluntários sobre o efetivo médio",
        "2025-09-30",
        "interval",
        (0.60, 0.80),
        0,
        ("pessoal",),
    ),
    (
        "Campus Kappa reabre o laboratório até 30/09",
        "Portaria de reabertura publicada e aulas práticas retomadas",
        "2025-09-30",
        "interval",
        (0.75, 0.95),
        1,
        ("operacao",),
    ),
    (
        "Sistema Lambda apresenta incidente de segurança explorado externamente",
        "Boletim de segurança confirmando exploração, com CVE atribuída",
        "2025-10-31",
        "point",
        0.55,
        1,
        ("seguranca",),
    ),
    (
        "Edital Mu é retificado antes do prazo de inscrição",
        "Retificação publicada no diário oficial antes do encerramento",
        "2025-10-31",
        "interval",
        (0.30, 0.50),
        1,
        ("publicacao",),
    ),
    (
        "Serviço Nu fica indisponível por mais de 1 hora em novembro",
        "Registro de indisponibilidade no status page, duração medida",
        "2025-11-30",
        "interval",
        (0.55, 0.75),
        0,
        ("infra",),
    ),
    (
        "Pesquisa Xi atinge 800 respondentes válidos",
        "Base final auditada com questionários completos",
        "2025-11-30",
        "point",
        0.75,
        0,
        ("pesquisa",),
    ),
    (
        "Contrato Omicron é assinado no ano fiscal corrente",
        "Contrato registrado no sistema financeiro com data de vigência",
        "2025-12-31",
        "interval",
        (0.40, 0.60),
        1,
        ("contrato",),
    ),
    (
        "Orçamento Pi é aprovado sem corte acima de 5%",
        "Ata de aprovação com o valor final consolidado",
        "2025-12-31",
        "interval",
        (0.35, 0.55),
        0,
        ("orcamento",),
    ),
    (
        "Time Rho entrega o painel até 31/01",
        "Painel em produção acessível aos usuários-chave, com aceite formal",
        "2026-01-31",
        "interval",
        (0.50, 0.70),
        1,
        ("programa",),
    ),
    (
        "Auditoria Sigma aponta ressalva no controle de acesso",
        "Relatório final de auditoria com a seção de achados",
        "2026-01-31",
        "point",
        0.30,
        0,
        ("auditoria",),
    ),
    (
        "Tau renova a certificação no primeiro semestre",
        "Certificado emitido e válido publicado no registro do órgão",
        "2026-06-30",
        "interval",
        (0.65, 0.85),
        0,
        ("certificacao",),
    ),
    (
        "Upsilon supera 10 mil usuários ativos no trimestre",
        "Métrica de produto no painel interno, média mensal",
        "2026-03-31",
        "interval",
        (0.35, 0.55),
        1,
        ("produto",),
    ),
    (
        "Phi fecha o trimestre com caixa acima de 2 milhões",
        "Demonstrativo financeiro assinado e publicado",
        "2026-03-31",
        "interval",
        (0.20, 0.40),
        0,
        ("financeiro",),
    ),
    (
        "Chi passa na inspeção sem itens críticos",
        "Laudo de inspeção com classificação final",
        "2026-04-30",
        "interval",
        (0.75, 0.95),
        1,
        ("operacao",),
    ),
    (
        "Psi tem pedido de renovação protocolado até 30/04",
        "Protocolo registrado no sistema com número verificável",
        "2026-04-30",
        "point",
        0.90,
        1,
        ("administrativo",),
    ),
    (
        "Omega perde o prazo de entrega em mais de 30 dias",
        "Cronograma oficial revisado com a nova data de entrega",
        "2026-05-31",
        "interval",
        (0.25, 0.60),
        1,
        ("programa",),
    ),
    (
        "Alfa-2 tem custo unitário acima do previsto em 20%",
        "Planilha de custos aprovada no comitê, comparada à linha de base",
        "2026-05-31",
        "interval",
        (0.55, 0.90),
        0,
        ("orcamento",),
    ),
    (
        "Beta-2 entra em operação assistida até junho",
        "Registro de go-live assistido com equipe dedicada",
        "2026-06-30",
        "interval",
        (0.45, 0.80),
        1,
        ("programa",),
    ),
    (
        "Gama-2 tem mais de 3 falhas de teste em produção",
        "Relatório de qualidade com contagem de falhas pós-deploy",
        "2026-06-30",
        "point",
        0.60,
        0,
        ("qualidade",),
    ),
    (
        "Delta-2 recebe parecer favorável do comitê de ética",
        "Parecer consubstanciado emitido e anexado ao processo",
        "2026-07-31",
        "interval",
        (0.70, 0.90),
        1,
        ("etica",),
    ),
    (
        "Épsilon-2 fica abaixo da meta de cobertura em 10 pontos",
        "Relatório de cobertura com a série histórica comparada",
        "2026-07-31",
        "interval",
        (0.15, 0.50),
        0,
        ("indicador",),
    ),
    (
        "Zeta-2 tem o contrato encerrado antes do prazo",
        "Distrato assinado e publicado, com data de encerramento",
        "2026-08-31",
        "interval",
        (0.20, 0.55),
        0,
        ("contrato",),
    ),
    (
        "Eta-2 entrega o relatório final no prazo",
        "Documento protocolado com carimbo de recebimento",
        "2026-08-31",
        "interval",
        (0.35, 0.70),
        1,
        ("publicacao",),
    ),
    (
        "Teta-2 fica acima do limite legal na medição anual",
        "Laudo técnico com a medição e o limite aplicável",
        "2026-09-30",
        "interval",
        (0.10, 0.80),
        1,
        ("conformidade",),
    ),
    (
        "Iota-2 tem o projeto cancelado no trimestre",
        "Ata de encerramento com a decisão registrada",
        "2026-09-30",
        "interval",
        (0.30, 1.00),
        0,
        ("programa",),
    ),
    (
        "Kappa-2 registra mais de 2 mil inscrições",
        "Relatório de inscrições homologadas",
        "2026-10-31",
        "interval",
        (0.05, 0.75),
        1,
        ("evento",),
    ),
    (
        "Lambda-2 tem o servidor substituído até outubro",
        "Ordem de serviço concluída e ativo baixado do inventário",
        "2026-10-31",
        "interval",
        (0.40, 1.00),
        1,
        ("infra",),
    ),
    (
        "Mu-2 tem o parecer publicado antes da reunião",
        "Parecer disponível no sistema antes da pauta",
        "2026-11-30",
        "interval",
        (0.15, 0.85),
        1,
        ("publicacao",),
    ),
    (
        "Nu-2 fica fora do ar no dia da eleição interna",
        "Registro de incidente com janela de indisponibilidade",
        "2026-11-30",
        "interval",
        (0.25, 0.95),
        0,
        ("infra",),
    ),
    (
        "Xi-2 aprova o orçamento com emenda",
        "Ata final com a emenda incorporada ao texto",
        "2026-12-31",
        "interval",
        (0.10, 1.00),
        1,
        ("orcamento",),
    ),
    (
        "Omicron-2 tem o pedido negado em primeira instância",
        "Decisão publicada com dispositivo e data",
        "2026-12-31",
        "interval",
        (0.35, 0.95),
        1,
        ("juridico",),
    ),
    (
        "Pi-2 conclui a fase de testes com 90% dos casos aprovados",
        "Relatório de testes com a taxa de aprovação consolidada",
        "2026-12-31",
        "interval",
        (0.00, 0.70),
        1,
        ("qualidade",),
    ),
    (
        "Rho-2 define o novo fornecedor até o fim do ano",
        "Contrato ou ata de seleção publicada",
        "2027-03-31",
        "interval",
        (0.50, 0.75),
        None,
        ("contrato",),
    ),
    (
        "Sigma-2 publica o balanço até março",
        "Demonstração publicada no portal, com parecer do conselho",
        "2027-06-30",
        "point",
        0.35,
        None,
        ("financeiro",),
    ),
    (
        "Tau-2 conclui a auditoria interna pendente",
        "Relatório final assinado pelo auditor responsável",
        "2026-10-31",
        "interval",
        (0.60, 0.85),
        None,
        ("auditoria",),
    ),
]

VOID_ROW = (
    "Upsilon-2 muda o escopo do projeto no semestre",
    "Ata de mudança de escopo aprovada",
    "2026-05-31",
    "interval",
    (0.30, 0.60),
)

ORIGIN_BY_INDEX = (
    "achlab:caso-alfa#H2",
    "negisc:brief-2025-03",
    "intel:brief-2025-11",
    "achlab:caso-beta#H1",
    "negisc:brief-2026-02",
    None,
)


def _timestamp(day: date, hour: int = 12) -> str:
    return f"{day.isoformat()}T{hour:02d}:00:00Z"


def build(root: str) -> Ledger:
    """Materialise the demo ledger at `root` (which must not exist yet)."""
    ledger = Ledger.init(root, ACTOR, ts=T0)
    created_ids: list[str] = []

    for index, (question, criteria, due, kind, value, outcome, tags) in enumerate(ROWS):
        lead = LEADS[index % len(LEADS)]
        created = date.fromisoformat(due) - timedelta(days=lead)
        entry = ledger.add(
            question=question,
            criteria=criteria,
            due=due,
            kind=kind,
            actor=ACTOR,
            point=value if kind == "point" else None,  # type: ignore[arg-type]
            interval=value if kind == "interval" else None,  # type: ignore[arg-type]
            tags=list(tags),
            origin=ORIGIN_BY_INDEX[index % len(ORIGIN_BY_INDEX)],
            created_at=_timestamp(created),
        )
        created_ids.append(entry.id)

    question, criteria, due, kind, value = VOID_ROW
    created = date.fromisoformat(due) - timedelta(days=LEADS[1])
    voided = ledger.add(
        question=question,
        criteria=criteria,
        due=due,
        kind=kind,
        actor=ACTOR,
        interval=value,  # type: ignore[arg-type]
        tags=["escopo"],
        origin="negisc:brief-2025-07",
        created_at=_timestamp(created),
    )

    for index, (_, _, due, _, _, outcome, _) in enumerate(ROWS):
        created = date.fromisoformat(due) - timedelta(days=LEADS[index % len(LEADS)])
        ledger.open_entry(created_ids[index], ACTOR, ts=_timestamp(created + timedelta(days=1)))
        if outcome is None:
            continue
        resolved_on = (
            date.fromisoformat(due) + timedelta(days=3)
            if index % 5 == 0
            else date.fromisoformat(due) - timedelta(days=1)
        )
        ledger.resolve(
            created_ids[index],
            outcome=outcome,
            evidence=Evidence(
                citation=f"Synthetic report {due}, section {index % 7 + 1}",
                url=f"https://example.org/reports/{due}",
                excerpt="Synthetic evidence recorded for the demo ledger.",
            ),
            resolver=ACTOR,
            resolved_at=_timestamp(resolved_on),
        )

    ledger.open_entry(voided.id, ACTOR, ts=_timestamp(created + timedelta(days=1)))
    ledger.void(
        voided.id,
        reason="Criterion ambiguous: no observation window was defined",
        resolver=ACTOR,
        ts=_timestamp(date.fromisoformat(due) + timedelta(days=9)),
    )
    return ledger

"""Book-level analysis reduce: terms, characters, T/V, style (roadmap 7.1)."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from frank.application.build_address import (
    AddressPorts,
    AddressReport,
    build_address_matrix,
    render_address_report,
)
from frank.application.build_characters import (
    CharacterPorts,
    CharacterReport,
    build_character_registry,
    render_character_report,
)
from frank.application.build_style import (
    StylePorts,
    StyleReport,
    build_style_card,
    render_style_report,
)
from frank.application.build_termbase import (
    TermbasePorts,
    TermbaseReport,
    TranslatePorts,
    TranslateReport,
    build_termbase,
    render_termbase_report,
    render_translate_report,
    translate_termbase,
)
from frank.domain.model.termbase import (
    AddressMatrixConfig,
    ChapterBriefConfig,
    CharacterEvidenceConfig,
    TermCollectConfig,
)


@dataclass(frozen=True)
class AnalyzePorts:
    termbase: TermbasePorts
    translate: TranslatePorts
    characters: CharacterPorts
    address: AddressPorts
    style: StylePorts


class AnalyzeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    terms: TermCollectConfig
    characters: CharacterEvidenceConfig
    address: AddressMatrixConfig
    briefs: ChapterBriefConfig


class AnalyzeReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    termbase: TermbaseReport
    translated: TranslateReport
    characters: CharacterReport
    addresses: AddressReport
    style: StyleReport


def analyze_book(
    ports: AnalyzePorts, slug: str, config: AnalyzeConfig
) -> AnalyzeReport:
    """Collect terms through the style card; one reduce after segmentation."""
    collected = build_termbase(ports.termbase, slug, config.terms)
    translated = translate_termbase(ports.translate, slug)
    characters = build_character_registry(ports.characters, slug, config.characters)
    addresses = build_address_matrix(ports.address, slug, config.address)
    style = build_style_card(ports.style, slug, config.briefs)
    return AnalyzeReport(
        slug=slug,
        termbase=collected,
        translated=translated,
        characters=characters,
        addresses=addresses,
        style=style,
    )


def render_analyze_report(report: AnalyzeReport) -> str:
    return (
        render_termbase_report(report.termbase)
        + render_translate_report(report.translated)
        + render_character_report(report.characters)
        + render_address_report(report.addresses)
        + render_style_report(report.style)
    )

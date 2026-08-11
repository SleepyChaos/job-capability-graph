from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class TechnologyPattern:
    alias_id: int
    normalized_alias: str
    l3_technology_node_id: int


@dataclass(frozen=True)
class TechnologyHit:
    alias_id: int
    l3_technology_node_id: int
    start_offset: int
    end_offset: int
    matched_text: str


def is_ascii_word(character: str) -> bool:
    return character.isascii() and (character.isalnum() or character == "_")


class TechnologyAliasMatcher:
    """A deterministic Aho-Corasick matcher with longest-overlap resolution."""

    def __init__(self, patterns: list[TechnologyPattern]):
        self.patterns = patterns
        self.transitions: list[dict[str, int]] = [{}]
        self.failures: list[int] = [0]
        self.outputs: list[list[int]] = [[]]
        for pattern_index, pattern in enumerate(patterns):
            state = 0
            for character in pattern.normalized_alias:
                next_state = self.transitions[state].get(character)
                if next_state is None:
                    next_state = len(self.transitions)
                    self.transitions[state][character] = next_state
                    self.transitions.append({})
                    self.failures.append(0)
                    self.outputs.append([])
                state = next_state
            self.outputs[state].append(pattern_index)
        self._build_failures()

    def _build_failures(self) -> None:
        queue: deque[int] = deque(self.transitions[0].values())
        while queue:
            state = queue.popleft()
            for character, next_state in self.transitions[state].items():
                queue.append(next_state)
                failure = self.failures[state]
                while failure and character not in self.transitions[failure]:
                    failure = self.failures[failure]
                self.failures[next_state] = self.transitions[failure].get(character, 0)
                self.outputs[next_state].extend(self.outputs[self.failures[next_state]])

    def find(self, text: str) -> list[TechnologyHit]:
        normalized_text = text.casefold()
        state = 0
        candidates: list[TechnologyHit] = []
        for index, character in enumerate(normalized_text):
            while state and character not in self.transitions[state]:
                state = self.failures[state]
            state = self.transitions[state].get(character, 0)
            for pattern_index in self.outputs[state]:
                pattern = self.patterns[pattern_index]
                end = index + 1
                start = end - len(pattern.normalized_alias)
                if start < 0 or not self._boundary_ok(
                    normalized_text, pattern.normalized_alias, start, end
                ):
                    continue
                candidates.append(
                    TechnologyHit(
                        alias_id=pattern.alias_id,
                        l3_technology_node_id=pattern.l3_technology_node_id,
                        start_offset=start,
                        end_offset=end,
                        matched_text=text[start:end],
                    )
                )
        return self._resolve_overlaps(candidates)

    @staticmethod
    def _boundary_ok(text: str, pattern: str, start: int, end: int) -> bool:
        if pattern and is_ascii_word(pattern[0]) and start > 0 and is_ascii_word(text[start - 1]):
            return False
        return not (
            pattern and is_ascii_word(pattern[-1]) and end < len(text) and is_ascii_word(text[end])
        )

    @staticmethod
    def _resolve_overlaps(candidates: list[TechnologyHit]) -> list[TechnologyHit]:
        selected: list[TechnologyHit] = []
        occupied_until = -1
        for hit in sorted(
            candidates,
            key=lambda item: (
                item.start_offset,
                -(item.end_offset - item.start_offset),
                item.alias_id,
            ),
        ):
            if hit.start_offset < occupied_until:
                continue
            selected.append(hit)
            occupied_until = hit.end_offset
        return selected

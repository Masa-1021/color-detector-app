#!/usr/bin/env python3
"""
マッピングルール評価エンジン

検出結果からルールを評価し、送信値を決定する。
"""

from typing import Dict, List

from .config_manager import (
    ConfigManager, Group, Rule, RuleCondition, DetectionResult
)


class RuleEngine:
    """マッピングルール評価エンジン"""

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager

    def evaluate_group(self, group: Group, results: List[DetectionResult]) -> int:
        """
        グループのルールを評価し、送信値を決定

        Args:
            group: グループ情報
            results: 全円の検出結果

        Returns:
            送信値（T1_STATUS）
        """
        # グループに属するルールを取得（優先度降順）
        group_rules = self.config.get_rules_for_group(group.id)

        # 検出結果をdict化（高速アクセス用）
        result_map = {r.circle_id: r for r in results}

        # ルールを順に評価
        for rule in group_rules:
            if self._evaluate_rule(rule, result_map):
                return rule.value

        # 全ルール不一致 → デフォルト値
        return group.default_value

    def _evaluate_rule(self, rule: Rule, result_map: Dict[int, DetectionResult]) -> bool:
        """
        1つのルールを評価

        Args:
            rule: ルール情報
            result_map: {circle_id: DetectionResult}

        Returns:
            ルールがマッチしたかどうか
        """
        if not rule.conditions:
            return False

        if rule.type == 'single':
            return self._evaluate_condition(rule.conditions[0], result_map)
        elif rule.type == 'composite':
            return self._evaluate_composite(rule.conditions, result_map)
        else:
            return False

    def _evaluate_condition(self, condition: RuleCondition,
                            result_map: Dict[int, DetectionResult]) -> bool:
        """
        単一条件を評価

        Args:
            condition: 条件
            result_map: 検出結果マップ

        Returns:
            条件がマッチしたかどうか
        """
        result = result_map.get(condition.circle_id)
        if not result:
            return False

        # 色が一致
        color_match = result.detected_color == condition.color

        # 点滅状態が一致
        blink_match = result.is_blinking == condition.blinking

        return color_match and blink_match

    def _evaluate_composite(self, conditions: List[RuleCondition],
                            result_map: Dict[int, DetectionResult]) -> bool:
        """
        複合条件を評価（AND条件）

        Args:
            conditions: 条件リスト
            result_map: 検出結果マップ

        Returns:
            全条件がマッチしたかどうか
        """
        for condition in conditions:
            if not self._evaluate_condition(condition, result_map):
                return False
        return True

    def evaluate_all_groups(self, results: List[DetectionResult]) -> Dict[int, int]:
        """
        全グループを評価

        Args:
            results: 全円の検出結果

        Returns:
            {group_id: value} の辞書
        """
        group_values = {}
        for group in self.config.groups:
            value = self.evaluate_group(group, results)
            group_values[group.id] = value
        return group_values

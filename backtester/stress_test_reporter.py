#!/usr/bin/env python3
"""
Stress Test Report Generator

Creates comprehensive reports from stress test results:
- Summary tables
- Per-algorithm scorecards
- Edge case comparison matrices
- HTML reports with visualizations
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from collections import defaultdict

from .stress_test_engine import StressTestMetrics, TestResult


class StressTestReporter:
    """Generate reports from stress test results"""
    
    def __init__(self, output_dir: str = "./stress_test_reports"):
        """
        Initialize reporter
        
        Args:
            output_dir: Directory for report output
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_report(
        self,
        all_results: Dict[str, List[StressTestMetrics]],
        timestamp: str = None
    ):
        """
        Generate comprehensive stress test report
        
        Args:
            all_results: Dict mapping algorithm_name -> list of metrics
            timestamp: Optional timestamp for filenames
        """
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Generate all report formats
        self._generate_json_report(all_results, timestamp)
        self._generate_text_summary(all_results, timestamp)
        self._generate_markdown_report(all_results, timestamp)
        self._generate_comparison_matrix(all_results, timestamp)
        
        print(f"\n{'='*70}")
        print(f"Reports generated in: {self.output_dir}")
        print(f"  • summary_{timestamp}.txt")
        print(f"  • report_{timestamp}.md")
        print(f"  • comparison_matrix_{timestamp}.md")
        print(f"  • results_{timestamp}.json")
        print(f"{'='*70}\n")
    
    def _generate_json_report(self, all_results: Dict[str, List[StressTestMetrics]], timestamp: str):
        """Save complete results as JSON"""
        output_file = self.output_dir / f"results_{timestamp}.json"
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'algorithms': {}
        }
        
        for algo_name, results in all_results.items():
            report['algorithms'][algo_name] = [r.to_dict() for r in results]
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
    
    def _generate_text_summary(self, all_results: Dict[str, List[StressTestMetrics]], timestamp: str):
        """Generate plain text summary"""
        output_file = self.output_dir / f"summary_{timestamp}.txt"
        
        lines = []
        lines.append("="*70)
        lines.append("STRESS TEST SUMMARY REPORT")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("="*70)
        lines.append("")
        
        # Overall stats
        total_algorithms = len(all_results)
        total_tests = sum(len(results) for results in all_results.values())
        
        lines.append(f"Algorithms Tested: {total_algorithms}")
        lines.append(f"Total Test Scenarios: {total_tests}")
        lines.append("")
        
        # Per-algorithm summary
        for algo_name, results in all_results.items():
            lines.append("-"*70)
            lines.append(f"Algorithm: {algo_name}")
            lines.append("-"*70)
            
            passed = sum(1 for r in results if r.result == TestResult.PASS)
            warnings = sum(1 for r in results if r.result == TestResult.WARNING)
            failed = sum(1 for r in results if r.result == TestResult.FAIL)
            errors = sum(1 for r in results if r.result == TestResult.ERROR)
            avg_score = sum(r.score for r in results) / len(results)
            
            lines.append(f"  Tests: {len(results)}")
            lines.append(f"  Passed: {passed} | Warnings: {warnings} | Failed: {failed} | Errors: {errors}")
            lines.append(f"  Average Score: {avg_score:.1f}/100")
            lines.append("")
            
            # Show each scenario
            for r in results:
                status_icon = {
                    TestResult.PASS: "✓",
                    TestResult.WARNING: "⚠",
                    TestResult.FAIL: "✗",
                    TestResult.ERROR: "❌"
                }.get(r.result, "?")
                
                lines.append(f"  {status_icon} {r.scenario_name:<30} {r.score:>5.1f}/100")
                
                if r.crashed:
                    lines.append(f"      ERROR: {r.error_message}")
                
                if r.issues:
                    for issue in r.issues:
                        lines.append(f"      - {issue}")
            
            lines.append("")
        
        # Rankings
        lines.append("="*70)
        lines.append("ALGORITHM RANKINGS")
        lines.append("="*70)
        lines.append("")
        
        rankings = []
        for algo_name, results in all_results.items():
            avg_score = sum(r.score for r in results) / len(results)
            passed = sum(1 for r in results if r.result == TestResult.PASS)
            rankings.append((algo_name, avg_score, passed, len(results)))
        
        rankings.sort(key=lambda x: (-x[1], -x[2]))  # Sort by score, then pass count
        
        for rank, (algo_name, avg_score, passed, total) in enumerate(rankings, 1):
            lines.append(f"{rank}. {algo_name:<30} Score: {avg_score:>5.1f}/100  Passed: {passed}/{total}")
        
        lines.append("")
        
        with open(output_file, 'w') as f:
            f.write('\n'.join(lines))
    
    def _generate_markdown_report(self, all_results: Dict[str, List[StressTestMetrics]], timestamp: str):
        """Generate markdown report"""
        output_file = self.output_dir / f"report_{timestamp}.md"
        
        lines = []
        lines.append("# Stress Test Report")
        lines.append("")
        lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Overview
        lines.append("## Overview")
        lines.append("")
        lines.append(f"- **Algorithms Tested**: {len(all_results)}")
        lines.append(f"- **Total Scenarios**: {sum(len(r) for r in all_results.values())}")
        lines.append("")
        
        # Summary table
        lines.append("## Algorithm Scores")
        lines.append("")
        lines.append("| Algorithm | Avg Score | Pass | Warn | Fail | Error | Grade |")
        lines.append("|-----------|-----------|------|------|------|-------|-------|")
        
        for algo_name, results in all_results.items():
            passed = sum(1 for r in results if r.result == TestResult.PASS)
            warnings = sum(1 for r in results if r.result == TestResult.WARNING)
            failed = sum(1 for r in results if r.result == TestResult.FAIL)
            errors = sum(1 for r in results if r.result == TestResult.ERROR)
            avg_score = sum(r.score for r in results) / len(results)
            
            if avg_score >= 80:
                grade = "A"
            elif avg_score >= 70:
                grade = "B"
            elif avg_score >= 60:
                grade = "C"
            else:
                grade = "F"
            
            lines.append(f"| {algo_name} | {avg_score:.1f} | {passed} | {warnings} | {failed} | {errors} | {grade} |")
        
        lines.append("")
        
        # Detailed results per algorithm
        lines.append("---")
        lines.append("")
        lines.append("## Detailed Results")
        lines.append("")
        
        for algo_name, results in all_results.items():
            lines.append(f"### {algo_name}")
            lines.append("")
            lines.append("| Scenario | Edge Case | Score | Result | Signals | Issues |")
            lines.append("|----------|-----------|-------|--------|---------|--------|")
            
            for r in results:
                result_emoji = {
                    TestResult.PASS: "✅",
                    TestResult.WARNING: "⚠️",
                    TestResult.FAIL: "❌",
                    TestResult.ERROR: "💥"
                }.get(r.result, "❓")
                
                issues_str = ", ".join(r.issues[:2]) if r.issues else "-"
                if len(r.issues) > 2:
                    issues_str += "..."
                
                lines.append(f"| {r.scenario_name} | {r.edge_case_type} | {r.score:.0f} | {result_emoji} | {r.total_signals} | {issues_str} |")
            
            lines.append("")
        
        with open(output_file, 'w') as f:
            f.write('\n'.join(lines))
    
    def _generate_comparison_matrix(self, all_results: Dict[str, List[StressTestMetrics]], timestamp: str):
        """Generate edge case comparison matrix"""
        output_file = self.output_dir / f"comparison_matrix_{timestamp}.md"
        
        lines = []
        lines.append("# Edge Case Comparison Matrix")
        lines.append("")
        lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Build matrix: edge_case -> algorithm -> metrics
        edge_cases = set()
        for results in all_results.values():
            for r in results:
                edge_cases.add(r.edge_case_type)
        
        edge_cases = sorted(edge_cases)
        
        for edge_case in edge_cases:
            lines.append(f"## {edge_case.replace('_', ' ').title()}")
            lines.append("")
            lines.append("| Algorithm | Score | Result | Signals | Exceptions | Key Issues |")
            lines.append("|-----------|-------|--------|---------|------------|------------|")
            
            for algo_name, results in all_results.items():
                # Find result for this edge case
                matching = [r for r in results if r.edge_case_type == edge_case]
                
                if matching:
                    r = matching[0]
                    result_emoji = {
                        TestResult.PASS: "✅",
                        TestResult.WARNING: "⚠️",
                        TestResult.FAIL: "❌",
                        TestResult.ERROR: "💥"
                    }.get(r.result, "❓")
                    
                    exceptions = len(r.exceptions_caught)
                    issue_summary = r.issues[0] if r.issues else "-"
                    
                    lines.append(f"| {algo_name} | {r.score:.0f} | {result_emoji} | {r.total_signals} | {exceptions} | {issue_summary} |")
                else:
                    lines.append(f"| {algo_name} | - | - | - | - | Not tested |")
            
            lines.append("")
        
        # Best/Worst per edge case
        lines.append("---")
        lines.append("")
        lines.append("## Edge Case Champions")
        lines.append("")
        lines.append("| Edge Case | Best Algorithm | Score |")
        lines.append("|-----------|----------------|-------|")
        
        for edge_case in edge_cases:
            best_score = 0
            best_algo = "None"
            
            for algo_name, results in all_results.items():
                matching = [r for r in results if r.edge_case_type == edge_case]
                if matching and matching[0].score > best_score:
                    best_score = matching[0].score
                    best_algo = algo_name
            
            lines.append(f"| {edge_case} | {best_algo} | {best_score:.0f} |")
        
        lines.append("")
        
        with open(output_file, 'w') as f:
            f.write('\n'.join(lines))
    
    def generate_html_report(self, all_results: Dict[str, List[StressTestMetrics]], timestamp: str):
        """Generate interactive HTML report (future enhancement)"""
        # TODO: Use plotly/matplotlib to create visualizations
        pass


if __name__ == "__main__":
    print("Stress Test Reporter")
    print("Use: python stress_test_runner.py to generate reports")

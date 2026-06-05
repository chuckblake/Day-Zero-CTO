#!/usr/bin/env ruby
# frozen_string_literal: true

require "cgi"
require "date"
require "fileutils"
require "json"
require "optparse"
require "pathname"

REPORT_FOLDERS = {
  "tech-stack" => "Tech Stack",
  "engineering-risk" => "Engineering Risk",
  "weekly-reviews" => "Weekly Reviews",
  "ceo-updates" => "CEO Updates",
  "decisions" => "Decisions",
  "code-reviews" => "Code Reviews"
}.freeze

CORE_DOCS = %w[
  STRATEGY.md
  TEAM.md
  OPERATING_CADENCE.md
  DECISIONS.md
  RISKS.md
].freeze

CORE_DOC_META = {
  "STRATEGY.md" => ["Strategy", "Stage, thesis, goals, constraints, and non-goals."],
  "TEAM.md" => ["Team", "People, roles, ownership, and open questions."],
  "OPERATING_CADENCE.md" => ["Operating Cadence", "Reviews, updates, planning rhythm, and ceremonies."],
  "DECISIONS.md" => ["Decisions", "Durable choices, rationale, owners, and revisit triggers."],
  "RISKS.md" => ["Risks", "Risk register, mitigations, owners, and review dates."]
}.freeze

options = {
  date: Date.today.iso8601
}

OptionParser.new do |parser|
  parser.banner = "Usage: dzcto-artifact.rb --project PATH [options]"

  parser.on("--project PATH", "Project folder; creates/uses PATH/knowledge/wiki") { |value| options[:project] = value }
  parser.on("--home PATH", "Legacy: wiki root folder") { |value| options[:home] = value }
  parser.on("--kind KIND", "Report kind: #{REPORT_FOLDERS.keys.join(", ")}") { |value| options[:kind] = value }
  parser.on("--title TITLE", "Report title") { |value| options[:title] = value }
  parser.on("--date DATE", "Report date, YYYY-MM-DD") { |value| options[:date] = value }
  parser.on("--body-file PATH", "Legacy: raw HTML body file; defaults to stdin when no --data-file is provided") { |value| options[:body_file] = value }
  parser.on("--data-file PATH", "Structured JSON report data file rendered by a built-in template") { |value| options[:data_file] = value }
  parser.on("--init", "Only ensure folder structure and index") { options[:init] = true }
end.parse!

abort "--project or --home is required" unless options[:project] || options[:home]

wiki_root =
  if options[:project]
    File.join(File.expand_path(options[:project]), "knowledge", "wiki")
  else
    File.expand_path(options[:home])
  end

project_folder =
  if options[:project]
    File.expand_path(options[:project])
  else
    File.expand_path(File.join(wiki_root, "..", ".."))
  end

core_dir = File.join(wiki_root, "core")
reports_dir = File.join(wiki_root, "reports")
learning_dir = File.join(wiki_root, "learning")

def slugify(value)
  value.downcase.gsub(/[^a-z0-9]+/, "-").gsub(/^-|-$/, "")
end

def escape(value)
  CGI.escapeHTML(value.to_s)
end

def markdown_section(path, heading)
  return nil unless File.exist?(path)

  lines = File.readlines(path, chomp: true)
  start_index = lines.index { |line| line.match?(/^##+\s+#{Regexp.escape(heading)}\s*$/i) }
  return nil unless start_index

  lines[(start_index + 1)..].take_while { |line| !line.match?(/^##+\s+\S/) }.join("\n").strip
end

def first_markdown_paragraph(text)
  text.to_s.split(/\n{2,}/).map(&:strip).find { |paragraph| !paragraph.empty? && !paragraph.start_with?("|", "-", "1.") }
end

def plain_markdown(value)
  value.to_s
       .gsub(/`([^`]+)`/, '\1')
       .gsub(/\[([^\]]+)\]\([^)]+\)/, '\1')
       .gsub(/\*\*|__/, "")
       .gsub(/\s+/, " ")
       .strip
end

def company_name(strategy_path, project_folder)
  if File.exist?(strategy_path)
    title = File.readlines(strategy_path, chomp: true).find { |line| line.start_with?("# ") }
    if title
      return title.sub(/^#\s+/, "").sub(/\s+Strategy\z/i, "").strip
    end
  end

  File.basename(project_folder)
end

def company_description(strategy_path)
  paragraph = first_markdown_paragraph(markdown_section(strategy_path, "Product Thesis")) ||
              first_markdown_paragraph(markdown_section(strategy_path, "Stage"))

  plain_markdown(paragraph || "Company context has not been captured yet. Add a Product Thesis section to core/STRATEGY.md to enrich this summary.")
end

def split_markdown_row(row)
  row.strip.sub(/\A\|/, "").sub(/\|\z/, "").split("|").map(&:strip)
end

def cadence_days(value)
  cadence = value.to_s.downcase

  return Regexp.last_match(1).to_i if cadence =~ /every\s+(\d+)\s+days?/
  return Regexp.last_match(1).to_i * 7 if cadence =~ /every\s+(\d+)\s+weeks?/
  return Regexp.last_match(1).to_i * 30 if cadence =~ /every\s+(\d+)\s+months?/
  return 1 if cadence.match?(/daily|once per day/)
  return 7 if cadence.match?(/weekly|once per week|every week/)
  return 14 if cadence.match?(/biweekly|every other week|fortnight/)
  return 30 if cadence.match?(/monthly|once per month|every month/)
  return 90 if cadence.match?(/quarterly|once per quarter|every quarter/)

  nil
end

def parse_cadence_rules(cadence_path)
  return [] unless File.exist?(cadence_path)

  lines = File.readlines(cadence_path, chomp: true)
  start_index = lines.index { |line| line.match?(/^##+\s+Index Cadence Rules\s*$/i) }
  return [] unless start_index

  section = lines[(start_index + 1)..].take_while { |line| !line.match?(/^##+\s+\S/) }
  table_lines = section.select { |line| line.strip.start_with?("|") }
  return [] if table_lines.length < 3

  headers = split_markdown_row(table_lines.first).map { |header| header.downcase.gsub(/[^a-z0-9]+/, "_").gsub(/\A_+|_+\z/, "") }
  rows = table_lines.drop(2)

  rows.map do |row|
    cells = split_markdown_row(row)
    values = headers.zip(cells).to_h
    folder = values["folder"] || values["report_folder"] || values["kind"]
    cadence = values["cadence"] || values["frequency"]
    command = values["command"] || values["prompt"] || values["run"]
    label = values["report"] || values["name"] || REPORT_FOLDERS[folder] || folder
    grace_days = Integer(values["grace_days"] || values["grace"] || 0, exception: false) || 0
    interval_days = cadence_days(cadence)

    next unless folder && cadence && command && interval_days

    {
      label: label,
      folder: folder,
      cadence: cadence,
      command: command,
      grace_days: grace_days,
      interval_days: interval_days
    }
  end.compact
end

def latest_report_date(reports_dir, folder)
  Dir.glob(File.join(reports_dir, folder, "*.html")).map do |path|
    match = File.basename(path).match(/\A(\d{4}-\d{2}-\d{2})-/)
    Date.iso8601(match[1]) if match
  rescue Date::Error
    nil
  end.compact.max
end

def cadence_alerts(cadence_rules, reports_dir, today)
  cadence_rules.map do |rule|
    latest_date = latest_report_date(reports_dir, rule[:folder])

    if latest_date
      due_date = latest_date + rule[:interval_days] + rule[:grace_days]
      next if today < due_date

      reason = "Last run #{latest_date.iso8601}; due #{due_date.iso8601}."
    else
      due_date = today
      reason = "No #{rule[:label]} report has been generated yet."
    end

    rule.merge(latest_date: latest_date, due_date: due_date, reason: reason)
  end.compact
end

def display_command(command)
  command.to_s
         .gsub(/\s*Use project folder `[^`]+`(?:\s+and read-only code repo `[^`]+`)?\.?/i, "")
         .gsub(/\s*Use read-only code repo `[^`]+`\.?/i, "")
         .strip
end

def default_help_commands(company)
  [
    ["Weekly CTO Review", "Run the weekly CTO review for #{company}."],
    ["CEO Update", "Write the CEO engineering update for #{company}."],
    ["Tech Stack", "Review the codebase and create a Tech Stack report for #{company}."],
    ["Engineering Risk Review", "Run the engineering risk review for #{company}."],
    ["Learning", "Run a Day Zero CTO learning prompt for #{company}."],
    ["Decision Help", "Help me work through a CTO decision for #{company}: <decision or problem>."],
    ["CTO Code Review", "Run a CTO code review for #{company} against <branch, PR, or diff>. Treat the repo as read-only unless I explicitly ask for code changes."]
  ]
end

def present?(value)
  case value
  when nil
    false
  when String
    !value.strip.empty?
  when Array, Hash
    !value.empty?
  else
    true
  end
end

def array_value(value)
  case value
  when nil
    []
  when Array
    value.compact.select { |item| present?(item) }
  else
    present?(value) ? [value] : []
  end
end

def value_at(hash, *keys)
  keys.each do |key|
    value = hash[key.to_s] || hash[key.to_sym]
    return value if present?(value)
  end

  nil
end

def text_value(value)
  case value
  when nil
    ""
  when Array
    value.map { |item| text_value(item) }.reject(&:empty?).join("; ")
  when Hash
    value.map { |key, item| "#{key}: #{text_value(item)}" }.reject { |part| part.end_with?(": ") }.join("; ")
  else
    value.to_s.strip
  end
end

def html_paragraph(value)
  text = text_value(value)
  return "" if text.empty?

  "<p>#{escape(text)}</p>"
end

def render_text_section(title, value)
  return "" unless present?(value)

  <<~HTML
    <section class="artifact-section">
      <h2>#{escape(title)}</h2>
      #{html_paragraph(value)}
    </section>
  HTML
end

def render_metrics(metrics)
  rows = array_value(metrics)
  return "" if rows.empty?

  cards = rows.map do |metric|
    if metric.is_a?(Hash)
      label = text_value(value_at(metric, "label", "name", "title"))
      value = text_value(value_at(metric, "value", "count", "status"))
      detail = text_value(value_at(metric, "detail", "note", "description"))
    else
      label = "Metric"
      value = text_value(metric)
      detail = ""
    end

    <<~HTML
      <div class="metric">
        <span class="label">#{escape(label)}</span>
        <span class="value">#{escape(value)}</span>
        #{detail.empty? ? "" : "<span class=\"detail\">#{escape(detail)}</span>"}
      </div>
    HTML
  end.join

  <<~HTML
    <div class="grid">
      #{cards}
    </div>
  HTML
end

def render_list_section(title, items)
  rows = array_value(items)
  return "" if rows.empty?

  list_items = rows.map do |item|
    if item.is_a?(Hash)
      title_text = text_value(value_at(item, "title", "name", "priority", "ask", "decision", "risk", "finding", "question", "prompt"))
      body = text_value(value_at(item, "body", "detail", "details", "summary", "why", "impact", "rationale", "note", "notes"))
      evidence = array_value(value_at(item, "evidence", "sources", "source"))
      owner = text_value(value_at(item, "owner", "owner_horizon", "needed_by", "done_when"))

      <<~HTML
        <li>
          #{title_text.empty? ? "" : "<strong>#{escape(title_text)}</strong>"}
          #{body.empty? ? "" : "<span>#{escape(body)}</span>"}
          #{owner.empty? ? "" : "<em>#{escape(owner)}</em>"}
          #{evidence.empty? ? "" : "<small>Evidence: #{escape(evidence.map { |entry| text_value(entry) }.reject(&:empty?).join("; "))}</small>"}
        </li>
      HTML
    else
      "<li>#{escape(text_value(item))}</li>"
    end
  end.join

  <<~HTML
    <section class="artifact-section">
      <h2>#{escape(title)}</h2>
      <ul class="artifact-list">
        #{list_items}
      </ul>
    </section>
  HTML
end

def severity_class(value)
  case text_value(value).downcase
  when /high|critical|block/
    "high"
  when /medium|moderate|watch/
    "medium"
  else
    "ready"
  end
end

def render_table_section(title, rows, columns)
  values = array_value(rows).select { |row| row.is_a?(Hash) }
  return "" if values.empty?

  headers = columns.map { |label, _key| "<th>#{escape(label)}</th>" }.join
  table_rows = values.map do |row|
    cells = columns.map do |_label, key|
      value = value_at(row, key)
      cell =
        if key.to_s.match?(/severity|likelihood|status/i) && present?(value)
          "<span class=\"tag #{severity_class(value)}\">#{escape(text_value(value))}</span>"
        else
          escape(text_value(value))
        end

      "<td>#{cell}</td>"
    end.join

    "<tr>#{cells}</tr>"
  end.join

  <<~HTML
    <section class="artifact-section">
      <h2>#{escape(title)}</h2>
      <table>
        <thead><tr>#{headers}</tr></thead>
        <tbody>#{table_rows}</tbody>
      </table>
    </section>
  HTML
end

def render_sources(data)
  sources = array_value(value_at(data, "sources", "source_list", "evidence_sources"))
  render_list_section("Sources", sources)
end

def render_weekly_review(data)
  [
    html_paragraph(value_at(data, "executive_read", "summary")),
    render_metrics(value_at(data, "metrics")),
    render_list_section("Shipped / Learned", value_at(data, "shipped_learned", "shipped", "learned")),
    render_table_section("Risks", value_at(data, "risks"), [
      ["Risk", "risk"],
      ["Evidence", "evidence"],
      ["Business Impact", "impact"],
      ["Severity", "severity"],
      ["Mitigation", "mitigation"]
    ]),
    render_table_section("Decisions Needed", value_at(data, "decisions_needed", "decisions"), [
      ["Decision", "decision"],
      ["Context", "context"],
      ["Owner", "owner"],
      ["Needed By", "needed_by"]
    ]),
    render_list_section("Team and Process", value_at(data, "team_process", "team_and_process")),
    render_table_section("Next-Week Focus", value_at(data, "next_week_focus", "next_focus", "priorities"), [
      ["Priority", "priority"],
      ["Owner", "owner"],
      ["Why", "why"],
      ["Done When", "done_when"]
    ]),
    render_list_section("CEO-Update Seeds", value_at(data, "ceo_update_seeds", "ceo_seeds")),
    render_sources(data)
  ].join
end

def render_ceo_update(data)
  [
    html_paragraph(value_at(data, "headline", "summary")),
    render_metrics(value_at(data, "metrics")),
    render_list_section("Progress", value_at(data, "progress")),
    render_list_section("Risks / Blockers", value_at(data, "risks_blockers", "risks", "blockers")),
    render_list_section("Asks / Decisions", value_at(data, "asks_decisions", "asks", "decisions")),
    render_list_section("Next", value_at(data, "next", "up_next")),
    render_sources(data)
  ].join
end

def render_engineering_risk(data)
  [
    html_paragraph(value_at(data, "executive_read", "summary")),
    render_metrics(value_at(data, "metrics")),
    render_table_section("Top Risks", value_at(data, "top_risks", "risks"), [
      ["Risk", "risk"],
      ["Evidence", "evidence"],
      ["Business Impact", "impact"],
      ["Likelihood", "likelihood"],
      ["Severity", "severity"],
      ["Mitigation", "mitigation"],
      ["Owner / Horizon", "owner_horizon"]
    ]),
    render_list_section("Mitigations", value_at(data, "mitigations")),
    render_list_section("Watchpoints", value_at(data, "watchpoints")),
    render_sources(data)
  ].join
end

def render_tech_stack(data)
  [
    html_paragraph(value_at(data, "executive_read", "summary")),
    render_table_section("Stack Components", value_at(data, "stack_components", "components"), [
      ["Layer", "layer"],
      ["Technology", "technology"],
      ["Evidence", "evidence"],
      ["Notes", "notes"]
    ]),
    render_text_section("Architecture Shape", value_at(data, "architecture_shape", "architecture")),
    render_list_section("Data and Storage", value_at(data, "data_storage", "data_and_storage")),
    render_list_section("Integrations", value_at(data, "integrations")),
    render_list_section("Infrastructure and Operations", value_at(data, "infrastructure_operations", "infrastructure", "operations")),
    render_list_section("Development Tooling", value_at(data, "development_tooling", "dev_tooling")),
    render_table_section("Risks and Watchpoints", value_at(data, "risks_watchpoints", "risks", "watchpoints"), [
      ["Risk", "risk"],
      ["Evidence", "evidence"],
      ["Impact", "impact"],
      ["Severity", "severity"],
      ["Mitigation", "mitigation"]
    ]),
    render_list_section("Onboarding Notes", value_at(data, "onboarding_notes", "notes")),
    render_sources(data)
  ].join
end

def render_decision(data)
  [
    render_text_section("Decision", value_at(data, "decision")),
    render_text_section("Context", value_at(data, "context")),
    render_table_section("Options", value_at(data, "options"), [
      ["Option", "option"],
      ["Upside", "upside"],
      ["Downside", "downside"],
      ["Reversibility", "reversibility"]
    ]),
    render_table_section("Tradeoffs", value_at(data, "tradeoffs"), [
      ["Axis", "axis"],
      ["Implication", "implication"],
      ["Note", "note"]
    ]),
    render_text_section("Recommendation", value_at(data, "recommendation")),
    render_list_section("Watchpoints", value_at(data, "watchpoints")),
    render_list_section("Follow-Ups", value_at(data, "follow_ups", "followups")),
    render_sources(data)
  ].join
end

def render_code_review(data)
  [
    render_text_section("Merge Recommendation", value_at(data, "merge_recommendation", "recommendation")),
    render_table_section("Blocking", value_at(data, "blocking"), [
      ["Finding", "finding"],
      ["Evidence", "evidence"],
      ["Impact", "impact"],
      ["Recommendation", "recommendation"]
    ]),
    render_table_section("FYI", value_at(data, "fyi"), [
      ["Finding", "finding"],
      ["Evidence", "evidence"],
      ["Impact", "impact"],
      ["Recommendation", "recommendation"]
    ]),
    render_table_section("Questions", value_at(data, "questions"), [
      ["Question", "question"],
      ["Why It Matters", "why"],
      ["Owner", "owner"]
    ]),
    render_text_section("Tests / Verification", value_at(data, "tests_verification", "verification")),
    render_text_section("Startup Risk Note", value_at(data, "startup_risk_note", "risk_note")),
    render_sources(data)
  ].join
end

def render_generic_report(data)
  summary = html_paragraph(value_at(data, "summary", "executive_read", "headline"))
  sections = array_value(value_at(data, "sections")).map do |section|
    next render_list_section("Section", [section]) unless section.is_a?(Hash)

    title = text_value(value_at(section, "title", "name"))
    content = value_at(section, "items", "body", "content", "details")
    content.is_a?(Array) ? render_list_section(title, content) : render_text_section(title, content)
  end.compact.join

  [summary, sections, render_sources(data)].join
end

def render_structured_report(kind, data)
  body =
    case kind
    when "tech-stack"
      render_tech_stack(data)
    when "weekly-reviews"
      render_weekly_review(data)
    when "ceo-updates"
      render_ceo_update(data)
    when "engineering-risk"
      render_engineering_risk(data)
    when "decisions"
      render_decision(data)
    when "code-reviews"
      render_code_review(data)
    else
      render_generic_report(data)
    end

  body.strip.empty? ? render_generic_report(data) : body
end

FileUtils.mkdir_p(core_dir)
REPORT_FOLDERS.each_key do |folder|
  FileUtils.mkdir_p(File.join(reports_dir, folder))
end
FileUtils.mkdir_p(File.join(wiki_root, "handoffs"))
FileUtils.mkdir_p(learning_dir)

written_report = nil

unless options[:init]
  abort "--kind is required unless --init is used" unless options[:kind]
  abort "--title is required unless --init is used" unless options[:title]
  abort "Unknown --kind '#{options[:kind]}'" unless REPORT_FOLDERS.key?(options[:kind])

  body =
    if options[:data_file]
      data_path = File.expand_path(options[:data_file])
      data = JSON.parse(File.read(data_path))
      abort "--data-file must contain a JSON object" unless data.is_a?(Hash)

      render_structured_report(options[:kind], data)
    elsif options[:body_file]
      File.read(File.expand_path(options[:body_file]))
    else
      STDIN.read
    end

  safe_title = escape(options[:title])
  safe_date = escape(options[:date])
  slug = slugify("#{options[:date]} #{options[:title]}")
  report_path = File.join(reports_dir, options[:kind], "#{slug}.html")

  html = <<~HTML
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>#{safe_title}</title>
        <style>
          :root { --ink: #172033; --muted: #5d6a7d; --line: #d9e0ea; --soft: #f6f8fb; --accent: #185a7d; }
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; margin: 0; color: var(--ink); background: #fff; }
          main { max-width: 980px; margin: 0 auto; padding: 44px 28px 64px; }
          h1, h2, h3 { line-height: 1.2; letter-spacing: 0; }
          h1 { font-size: 34px; margin: 0 0 6px; }
          h2 { font-size: 23px; margin-top: 34px; border-top: 1px solid var(--line); padding-top: 24px; }
          h3 { font-size: 18px; margin-top: 24px; }
          .meta, .nav { color: var(--muted); }
          .meta { margin: 0 0 30px; }
          .nav { margin: 0 0 22px; font-size: 14px; }
          a { color: var(--accent); }
          table { border-collapse: collapse; width: 100%; margin: 16px 0 24px; font-size: 14px; }
          th, td { border: 1px solid var(--line); padding: 9px; vertical-align: top; text-align: left; }
          th { background: var(--soft); }
          code { background: var(--soft); border: 1px solid var(--line); padding: 0.1rem 0.25rem; border-radius: 4px; }
          .callout { background: var(--soft); border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin: 18px 0; }
          .artifact-section { margin-top: 34px; border-top: 1px solid var(--line); padding-top: 24px; }
          .artifact-section:first-of-type { margin-top: 0; border-top: 0; padding-top: 0; }
          .artifact-list { display: grid; gap: 10px; margin: 16px 0 24px; padding: 0; list-style: none; }
          .artifact-list li { border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
          .artifact-list strong, .artifact-list span, .artifact-list em, .artifact-list small { display: block; }
          .artifact-list span, .artifact-list em, .artifact-list small { margin-top: 4px; color: var(--muted); }
          .artifact-list em, .artifact-list small { font-size: 13px; font-style: normal; }
          .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 20px 0 6px; }
          .metric { border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fff; }
          .metric .label { color: var(--muted); font-size: 13px; }
          .metric .value { display: block; margin-top: 5px; font-size: 22px; font-weight: 700; }
          .metric .detail { display: block; color: var(--muted); font-size: 13px; margin-top: 4px; }
          .tag { display: inline-block; border-radius: 999px; padding: 2px 8px; font-size: 12px; font-weight: 700; white-space: nowrap; }
          .high { color: #9f1d25; background: #ffe8eb; }
          .medium { color: #8a4b00; background: #fff4df; }
          .ready { color: #16633d; background: #e8f6ef; }
          .source-list { font-size: 14px; color: var(--muted); }
          @media (max-width: 760px) { main { padding: 28px 18px 48px; } .grid { grid-template-columns: 1fr; } table { display: block; overflow-x: auto; } }
        </style>
      </head>
      <body>
        <main>
          <p class="nav"><a href="../../index.html">Knowledge wiki index</a></p>
          <h1>#{safe_title}</h1>
          <p class="meta">#{safe_date} · #{escape(REPORT_FOLDERS[options[:kind]])}</p>
          #{body}
        </main>
      </body>
    </html>
  HTML

  File.write(report_path, html)
  written_report = report_path
end

def report_links(wiki_root, kind)
  pattern = File.join(wiki_root, "reports", kind, "*.html")
  Dir.glob(pattern).sort.reverse
end

def report_run_date(path)
  match = File.basename(path).match(/\A(\d{4}-\d{2}-\d{2})-/)
  match ? match[1] : "Unknown date"
end

def report_name(path)
  File.basename(path, ".html").sub(/^\d{4}-\d{2}-\d{2}-/, "").tr("-", " ")
end

def pluralize(count, singular, plural = nil)
  "#{count} #{count == 1 ? singular : (plural || "#{singular}s")}"
end

def read_learning_items(learning_dir)
  path = File.join(learning_dir, "items.json")
  return [] unless File.exist?(path)

  items = JSON.parse(File.read(path))
  items.is_a?(Array) ? items : []
rescue JSON::ParserError
  []
end

def read_learning_reviews(learning_dir)
  path = File.join(learning_dir, "reviews.jsonl")
  return [] unless File.exist?(path)

  File.readlines(path, chomp: true).map do |line|
    JSON.parse(line)
  rescue JSON::ParserError
    nil
  end.compact
end

def date_value(value)
  Date.iso8601(value.to_s)
rescue Date::Error
  nil
end

def active_learning_items(items)
  items.select { |item| item.fetch("status", "active") == "active" }
end

def learning_counts(items, today)
  active = active_learning_items(items)
  new_count = active.count { |item| item.fetch("seen_count", 0).to_i.zero? }
  due_count = active.count do |item|
    due_on = date_value(item["due_on"])
    item.fetch("seen_count", 0).to_i.positive? && due_on && due_on <= today
  end

  {
    active: active.length,
    due: due_count,
    new: new_count
  }
end

def learning_summary(items, today)
  counts = learning_counts(items, today)
  parts = [pluralize(counts[:active], "learning item")]
  parts << "#{counts[:due]} due" if counts[:due].positive?
  parts << "#{counts[:new]} new" if counts[:new].positive?
  parts.join(" · ")
end

def learning_item_status(item, today)
  return "New" if item.fetch("seen_count", 0).to_i.zero?

  due_on = date_value(item["due_on"])
  return "Due" if due_on && due_on <= today

  "Scheduled"
end

def write_learning_index(wiki_root, company, items, reviews, today)
  learning_dir = File.join(wiki_root, "learning")
  FileUtils.mkdir_p(learning_dir)

  active = active_learning_items(items).sort_by do |item|
    [
      item.fetch("seen_count", 0).to_i.zero? ? 0 : 1,
      item["due_on"].to_s,
      item["title"].to_s.downcase
    ]
  end

  item_rows =
    if active.empty?
      <<~HTML
        <tr>
          <td colspan="7" class="empty-item">No learning items yet. Run the learning skill to add the first system concept.</td>
        </tr>
      HTML
    else
      active.map do |item|
        <<~HTML
          <tr>
            <td><strong>#{escape(item["title"])}</strong><br><span>#{escape(item["summary"])}</span></td>
            <td>#{escape(learning_item_status(item, today))}</td>
            <td>#{escape(item["due_on"] || "Unknown")}</td>
            <td>#{escape(item.fetch("box", 0))}</td>
            <td>#{escape(item.fetch("seen_count", 0))}</td>
            <td>#{escape(item["last_rating"] || "Not reviewed")}</td>
            <td>#{escape(item["source"] || "Unknown")}</td>
          </tr>
        HTML
      end.join
    end

  review_rows =
    if reviews.empty?
      "<li class=\"empty-item\">No reviews logged yet.</li>"
    else
      reviews.last(12).reverse.map do |review|
        title = review["title"] || review["id"]
        "<li><strong>#{escape(review["reviewed_on"])}</strong> #{escape(title)} - #{escape(review["rating_label"] || review["rating"])}, next due #{escape(review["due_on"])}</li>"
      end.join("\n")
    end

  counts = learning_counts(items, today)
  html = <<~HTML
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>#{escape(company)} Learning</title>
        <style>
          :root { --ink: #172033; --muted: #5d6a7d; --line: #d9e0ea; --soft: #f6f8fb; --accent: #185a7d; }
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; margin: 0; color: var(--ink); background: #fff; }
          main { max-width: 980px; margin: 0 auto; padding: 44px 28px 64px; }
          h1, h2 { line-height: 1.2; letter-spacing: 0; }
          h1 { font-size: 34px; margin: 0 0 8px; }
          h2 { font-size: 22px; margin-top: 32px; border-top: 1px solid var(--line); padding-top: 22px; }
          p, span, li { color: var(--muted); }
          a { color: var(--accent); }
          .nav { color: var(--muted); font-size: 14px; margin-bottom: 22px; }
          .summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 22px 0; }
          .metric { border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
          .metric span { display: block; font-size: 13px; }
          .metric strong { display: block; font-size: 22px; margin-top: 4px; }
          table { width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 14px; }
          th, td { border: 1px solid var(--line); padding: 9px; text-align: left; vertical-align: top; }
          th { background: var(--soft); }
          code { background: var(--soft); border: 1px solid var(--line); border-radius: 4px; padding: 1px 4px; }
          .empty-item { color: var(--muted); }
          @media (max-width: 760px) { main { padding: 28px 18px 48px; } .summary { grid-template-columns: 1fr; } table { display: block; overflow-x: auto; } }
        </style>
      </head>
      <body>
        <main>
          <p class="nav"><a href="../index.html">Knowledge wiki index</a></p>
          <h1>#{escape(company)} Learning</h1>
          <p>Spaced repetition for system knowledge. The learning skill presents one system concept, asks for a self-rating, and schedules the next review from that answer.</p>
          <div class="summary">
            <div class="metric"><span>Active</span><strong>#{counts[:active]}</strong></div>
            <div class="metric"><span>Due</span><strong>#{counts[:due]}</strong></div>
            <div class="metric"><span>New</span><strong>#{counts[:new]}</strong></div>
          </div>
          <h2>How Scoring Works</h2>
          <p>Reply with <code>Needs Work</code>, <code>Familiar</code>, or <code>Confident</code>. Needs Work brings the item back tomorrow, Familiar moves it forward one box, and Confident moves it forward two boxes.</p>
          <h2>Items</h2>
          <table>
            <thead>
              <tr>
                <th>Item</th>
                <th>Status</th>
                <th>Due</th>
                <th>Box</th>
                <th>Seen</th>
                <th>Last rating</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              #{item_rows}
            </tbody>
          </table>
          <h2>Recent Reviews</h2>
          <ul>
            #{review_rows}
          </ul>
        </main>
      </body>
    </html>
  HTML

  File.write(File.join(learning_dir, "index.html"), html)
end

report_entries = REPORT_FOLDERS.map do |folder, label|
  [folder, label, report_links(wiki_root, folder)]
end

report_count = report_entries.sum { |_folder, _label, links| links.length }

report_sections = report_entries.map do |folder, label, links|
  items =
    if links.empty?
      "<li class=\"empty-item\">No reports yet.</li>"
    else
      links.map do |path|
        relative = Pathname.new(path).relative_path_from(Pathname.new(wiki_root)).to_s
        <<~HTML
          <li class="report-link">
            <span class="report-date">#{escape(report_run_date(path))}</span>
            <a href="#{escape(relative)}">#{escape(report_name(path))}</a>
          </li>
        HTML
      end.join("\n")
  end

  <<~HTML
    <section class="report-section">
      <h2>#{escape(label)}</h2>
      <ul class="report-list">
        #{items}
      </ul>
    </section>
  HTML
end.join("\n")

core_links = CORE_DOCS.map do |doc|
  path = File.join(core_dir, doc)
  title, description = CORE_DOC_META.fetch(doc, [doc, "Core CTO context."])

  if File.exist?(path)
    <<~HTML
      <a class="core-card" href="core/#{escape(doc)}">
        <span class="core-title">#{escape(title)}</span>
        <span class="core-desc">#{escape(description)}</span>
        <span class="core-file">#{escape(doc)}</span>
      </a>
    HTML
  else
    <<~HTML
      <div class="core-card missing-card">
        <span class="core-title">#{escape(title)}</span>
        <span class="core-desc">#{escape(description)}</span>
        <span class="core-file">#{escape(doc)} not created yet</span>
      </div>
    HTML
  end
end.join

handoff_paths = Dir.glob(File.join(wiki_root, "handoffs", "**", "*")).select { |path| File.file?(path) }.sort
handoff_links =
  if handoff_paths.empty?
    "<li class=\"empty-item\">No handoffs yet.</li>"
  else
    handoff_paths.map do |path|
      relative = Pathname.new(path).relative_path_from(Pathname.new(wiki_root)).to_s
      name = File.basename(path).sub(/\.(html|md|txt)\z/i, "").tr("-", " ")
      "<li><a href=\"#{escape(relative)}\">#{escape(name)}</a></li>"
    end.join("\n")
  end

cadence_rules = parse_cadence_rules(File.join(core_dir, "OPERATING_CADENCE.md"))
alerts = cadence_alerts(cadence_rules, reports_dir, Date.today)
strategy_path = File.join(core_dir, "STRATEGY.md")
company = company_name(strategy_path, project_folder)
description = company_description(strategy_path)
learning_items = read_learning_items(learning_dir)
learning_reviews = read_learning_reviews(learning_dir)
write_learning_index(wiki_root, company, learning_items, learning_reviews, Date.today)
cadence_status_html =
  if cadence_rules.empty?
    ""
  elsif alerts.empty?
    <<~HTML
      <div class="cadence-watch">
        <h2>Cadence Watch</h2>
        <p>All scheduled report cadences are current.</p>
      </div>
    HTML
  else
    alert_cards = alerts.map do |alert|
      <<~HTML
        <div class="cadence-alert">
          <div>
            <strong>#{escape(alert[:label])}</strong>
            <span>#{escape(alert[:reason])}</span>
          </div>
          <code>#{escape(display_command(alert[:command]))}</code>
        </div>
      HTML
    end.join

    <<~HTML
      <div class="cadence-watch cadence-watch-alert">
        <h2>Cadence Alerts</h2>
        <p>Generated from <a href="core/OPERATING_CADENCE.md">OPERATING_CADENCE.md</a>.</p>
        <div class="cadence-list">
          #{alert_cards}
        </div>
      </div>
    HTML
  end

report_status =
  if cadence_rules.empty?
    pluralize(report_count, "artifact")
  elsif alerts.empty?
    "#{pluralize(report_count, "artifact")} · All current"
  else
    "#{pluralize(report_count, "artifact")} · #{pluralize(alerts.length, "alert")}"
  end

learning_status = learning_summary(learning_items, Date.today)
misc_status = pluralize(handoff_paths.length, "handoff")

help_commands = (cadence_rules.map { |rule| [rule[:label], display_command(rule[:command])] } + default_help_commands(company))
seen_commands = {}
help_entries = help_commands.map do |label, command|
  normalized = command.downcase
  next if command.empty? || seen_commands[normalized]

  seen_commands[normalized] = true
  [label, command]
end.compact

help_items = help_entries.map do |label, command|
  <<~HTML
    <div class="help-command">
      <strong>#{escape(label)}</strong>
      <code>#{escape(command)}</code>
    </div>
  HTML
end.join

index_html = <<~HTML
  <!doctype html>
  <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>#{escape(company)} Day Zero CTO Knowledge Wiki</title>
      <style>
        :root { --ink: #172033; --muted: #5d6a7d; --line: #d9e0ea; --soft: #f6f8fb; --accent: #185a7d; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; margin: 0; color: var(--ink); background: #fff; }
        main { max-width: 960px; margin: 0 auto; padding: 44px 28px 64px; }
        h1, h2 { line-height: 1.2; letter-spacing: 0; }
        h1 { font-size: 34px; margin: 0 0 8px; }
        h2 { font-size: 22px; margin: 0 0 12px; }
        p { color: var(--muted); margin: 0 0 18px; }
        section { margin-top: 30px; border-top: 1px solid var(--line); padding-top: 24px; }
        a { color: var(--accent); text-decoration: none; }
        a:hover { text-decoration: underline; }
        ul { margin: 12px 0 0 20px; padding: 0; }
        li { margin: 6px 0; }
        .missing { color: var(--muted); }
        .company-label { color: var(--muted); font-size: 14px; font-weight: 700; margin: 0 0 8px; text-transform: uppercase; }
        .company-description { font-size: 17px; margin-bottom: 12px; }
        .report-list { margin-left: 0; list-style: none; }
      .report-link { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 14px; align-items: baseline; }
      .report-date { color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
      .cadence-watch { margin: 6px 0 22px; }
      .cadence-watch p { margin-bottom: 12px; }
      .cadence-list { display: grid; gap: 10px; }
      .cadence-alert { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; border: 1px solid #e2b454; border-radius: 8px; background: #fff8e6; padding: 12px; }
        .cadence-alert strong { display: block; margin-bottom: 2px; }
        .cadence-alert span { color: var(--muted); font-size: 14px; }
        .cadence-alert code { display: block; white-space: normal; overflow-wrap: anywhere; background: #fff; border: 1px solid #ead49a; border-radius: 6px; padding: 8px; color: var(--ink); }
        .help-section p { max-width: 840px; }
      .help-grid { display: grid; gap: 10px; margin-top: 14px; }
      .help-command { display: grid; grid-template-columns: 180px minmax(0, 1fr); gap: 14px; align-items: start; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
      .help-command code { white-space: normal; overflow-wrap: anywhere; background: var(--soft); border: 1px solid var(--line); border-radius: 6px; padding: 7px; color: var(--ink); }
      .wiki-details { margin-top: 30px; border-top: 1px solid var(--line); padding-top: 24px; }
      .wiki-details summary { display: flex; align-items: center; justify-content: space-between; gap: 18px; cursor: pointer; list-style: none; }
      .wiki-details summary::-webkit-details-marker { display: none; }
      .wiki-heading { display: flex; align-items: center; gap: 10px; font-size: 22px; font-weight: 700; line-height: 1.2; }
      .wiki-chevron { width: 8px; height: 8px; border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted); transform: rotate(-45deg); transition: transform 0.15s ease; }
      .wiki-details[open] .wiki-chevron { transform: rotate(45deg); }
      .wiki-meta { color: var(--muted); font-size: 14px; text-align: right; white-space: nowrap; }
      .wiki-body { margin-top: 14px; }
      .core-list { display: grid; grid-template-columns: 1fr; gap: 8px; margin-top: 12px; }
      .core-card { display: grid; grid-template-columns: 220px minmax(0, 1fr) 190px; gap: 18px; align-items: center; box-sizing: border-box; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; color: var(--ink); }
      .core-card:hover { text-decoration: none; background: var(--soft); }
        .core-title { font-weight: 700; }
      .core-desc { color: var(--muted); font-size: 14px; }
      .core-file { color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; text-align: right; white-space: nowrap; }
      .missing-card { background: var(--soft); }
      .report-section { margin-top: 20px; border-top: 1px solid var(--line); padding-top: 18px; }
      .report-section:first-of-type { margin-top: 0; border-top: 0; padding-top: 0; }
      .misc-section { margin-top: 0; border-top: 0; padding-top: 0; }
      .misc-section + .misc-section { margin-top: 20px; border-top: 1px solid var(--line); padding-top: 18px; }
      .inline-meta { color: var(--muted); font-size: 14px; margin-left: 6px; }
      .empty-item { color: var(--muted); }
      @media (max-width: 760px) { main { padding: 28px 18px 48px; } .report-link, .help-command { grid-template-columns: 1fr; gap: 4px; } .wiki-details summary { align-items: flex-start; } .wiki-meta { text-align: left; white-space: normal; } .core-card { grid-template-columns: 1fr; gap: 3px; } .core-file { text-align: left; white-space: normal; } }
      </style>
    </head>
    <body>
      <main>
        <p class="company-label">For #{escape(company)}</p>
        <h1>#{escape(company)} Day Zero CTO Knowledge Wiki</h1>
        <p class="company-description">#{escape(description)}</p>

        <details class="wiki-details">
          <summary>
            <span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Core Context</span>
            <span class="wiki-meta">#{pluralize(CORE_DOCS.length, "file")}</span>
          </summary>
          <div class="wiki-body core-list">
            #{core_links}
          </div>
        </details>

        <details class="wiki-details">
          <summary>
            <span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Reports</span>
            <span class="wiki-meta">#{escape(report_status)}</span>
          </summary>
          <div class="wiki-body">
            #{cadence_status_html}
            #{report_sections}
          </div>
        </details>

        <details class="wiki-details">
          <summary>
            <span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Learning</span>
            <span class="wiki-meta">#{escape(learning_status)}</span>
          </summary>
          <div class="wiki-body">
            <ul>
              <li><a href="learning/index.html">Spaced repetition learning</a><span class="inline-meta">#{escape(learning_status)}</span></li>
            </ul>
          </div>
        </details>

        <details class="wiki-details help-section">
          <summary>
            <span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Help</span>
            <span class="wiki-meta">#{pluralize(help_entries.length, "command")}</span>
          </summary>
          <div class="wiki-body">
            <p>Ask your agent with one of these commands. The command can be pasted as-is, then refined with the current decision, person, branch, or review target.</p>
            <div class="help-grid">
              #{help_items}
            </div>
          </div>
        </details>

        <details class="wiki-details">
          <summary>
            <span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Misc</span>
            <span class="wiki-meta">#{escape(misc_status)}</span>
          </summary>
          <div class="wiki-body">
            <section class="misc-section">
              <h2>Handoffs</h2>
              <ul>
                #{handoff_links}
              </ul>
            </section>
          </div>
        </details>
      </main>
    </body>
  </html>
HTML

File.write(File.join(wiki_root, "index.html"), index_html)

puts written_report || File.join(wiki_root, "index.html")

#!/usr/bin/env ruby
# frozen_string_literal: true

require "cgi"
require "date"
require "fileutils"
require "optparse"
require "pathname"

REPORT_FOLDERS = {
  "engineering-risk" => "Engineering Risk",
  "weekly-reviews" => "Weekly Reviews",
  "ceo-updates" => "CEO Updates",
  "one-on-ones" => "One-on-Ones",
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
  parser.on("--body-file PATH", "HTML body file; defaults to stdin") { |value| options[:body_file] = value }
  parser.on("--init", "Only ensure folder structure and index") { options[:init] = true }
end.parse!

abort "--project or --home is required" unless options[:project] || options[:home]

wiki_root =
  if options[:project]
    File.join(File.expand_path(options[:project]), "knowledge", "wiki")
  else
    File.expand_path(options[:home])
  end

core_dir = File.join(wiki_root, "core")
reports_dir = File.join(wiki_root, "reports")

def slugify(value)
  value.downcase.gsub(/[^a-z0-9]+/, "-").gsub(/^-|-$/, "")
end

def escape(value)
  CGI.escapeHTML(value.to_s)
end

FileUtils.mkdir_p(core_dir)
REPORT_FOLDERS.each_key do |folder|
  FileUtils.mkdir_p(File.join(reports_dir, folder))
end
FileUtils.mkdir_p(File.join(wiki_root, "handoffs"))

written_report = nil

unless options[:init]
  abort "--kind is required unless --init is used" unless options[:kind]
  abort "--title is required unless --init is used" unless options[:title]
  abort "Unknown --kind '#{options[:kind]}'" unless REPORT_FOLDERS.key?(options[:kind])

  body =
    if options[:body_file]
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
          .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 20px 0 6px; }
          .metric { border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fff; }
          .metric .label { color: var(--muted); font-size: 13px; }
          .metric .value { display: block; margin-top: 5px; font-size: 22px; font-weight: 700; }
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

index_sections = REPORT_FOLDERS.map do |folder, label|
  links = report_links(wiki_root, folder)
  items =
    if links.empty?
      "<li>No reports yet.</li>"
    else
      links.map do |path|
        relative = Pathname.new(path).relative_path_from(Pathname.new(wiki_root)).to_s
        name = File.basename(path, ".html").sub(/^\d{4}-\d{2}-\d{2}-/, "").tr("-", " ")
        "<li><a href=\"#{escape(relative)}\">#{escape(name)}</a></li>"
      end.join("\n")
    end

  <<~HTML
    <section>
      <h2>#{escape(label)}</h2>
      <ul>
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
    "<li>No handoffs yet.</li>"
  else
    handoff_paths.map do |path|
      relative = Pathname.new(path).relative_path_from(Pathname.new(wiki_root)).to_s
      name = File.basename(path).sub(/\.(html|md|txt)\z/i, "").tr("-", " ")
      "<li><a href=\"#{escape(relative)}\">#{escape(name)}</a></li>"
    end.join("\n")
  end

index_html = <<~HTML
  <!doctype html>
  <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Day Zero CTO Knowledge Wiki</title>
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
        .path { background: var(--soft); border: 1px solid var(--line); border-radius: 8px; padding: 14px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 14px; color: var(--muted); }
        .core-details { margin-top: 30px; border-top: 1px solid var(--line); padding-top: 24px; }
        .core-details summary { display: flex; align-items: center; justify-content: space-between; gap: 18px; cursor: pointer; list-style: none; }
        .core-details summary::-webkit-details-marker { display: none; }
        .core-heading { display: flex; align-items: center; gap: 10px; font-size: 22px; font-weight: 700; line-height: 1.2; }
        .core-chevron { width: 8px; height: 8px; border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted); transform: rotate(-45deg); transition: transform 0.15s ease; }
        .core-details[open] .core-chevron { transform: rotate(45deg); }
        .core-count { color: var(--muted); font-size: 14px; white-space: nowrap; }
        .core-list { display: grid; grid-template-columns: 1fr; gap: 8px; margin-top: 12px; }
        .core-card { display: grid; grid-template-columns: 220px minmax(0, 1fr) 190px; gap: 18px; align-items: center; box-sizing: border-box; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; color: var(--ink); }
        .core-card:hover { text-decoration: none; background: var(--soft); }
        .core-title { font-weight: 700; }
        .core-desc { color: var(--muted); font-size: 14px; }
        .core-file { color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; text-align: right; white-space: nowrap; }
        .missing-card { background: var(--soft); }
        @media (max-width: 760px) { main { padding: 28px 18px 48px; } .core-details summary { align-items: flex-start; } .core-card { grid-template-columns: 1fr; gap: 3px; } .core-file { text-align: left; white-space: normal; } }
      </style>
    </head>
    <body>
      <main>
        <h1>Day Zero CTO Knowledge Wiki</h1>
        <p>Bookmark this page to reach the startup's CTO context, reports, reviews, decisions, and handoffs.</p>
        <div class="path">#{escape(wiki_root)}</div>

        <details class="core-details">
          <summary>
            <span class="core-heading"><span class="core-chevron" aria-hidden="true"></span>Core Context</span>
            <span class="core-count">#{CORE_DOCS.length} files</span>
          </summary>
          <div class="core-list">
            #{core_links}
          </div>
        </details>

        #{index_sections}

        <section>
          <h2>Handoffs</h2>
          <ul>
            #{handoff_links}
          </ul>
        </section>
      </main>
    </body>
  </html>
HTML

File.write(File.join(wiki_root, "index.html"), index_html)

puts written_report || File.join(wiki_root, "index.html")

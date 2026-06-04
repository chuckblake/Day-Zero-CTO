#!/usr/bin/env ruby
# frozen_string_literal: true

require "cgi"
require "date"
require "fileutils"
require "optparse"

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

options = {
  date: Date.today.iso8601
}

OptionParser.new do |parser|
  parser.banner = "Usage: dzcto-artifact.rb --home PATH [options]"

  parser.on("--home PATH", "Day Zero CTO home folder") { |value| options[:home] = value }
  parser.on("--kind KIND", "Report kind: #{REPORT_FOLDERS.keys.join(", ")}") { |value| options[:kind] = value }
  parser.on("--title TITLE", "Report title") { |value| options[:title] = value }
  parser.on("--date DATE", "Report date, YYYY-MM-DD") { |value| options[:date] = value }
  parser.on("--body-file PATH", "HTML body file; defaults to stdin") { |value| options[:body_file] = value }
  parser.on("--init", "Only ensure folder structure and index") { options[:init] = true }
end.parse!

abort "--home is required" unless options[:home]

home = File.expand_path(options[:home])
core_dir = File.join(home, "core")
reports_dir = File.join(home, "reports")

def slugify(value)
  value.downcase.gsub(/[^a-z0-9]+/, "-").gsub(/^-|-$/, "")
end

def escape(value)
  CGI.escapeHTML(value.to_s)
end

def relative_link(from_dir, target)
  Pathname.new(target).relative_path_from(Pathname.new(from_dir)).to_s
end

require "pathname"

FileUtils.mkdir_p(core_dir)
REPORT_FOLDERS.each_key do |folder|
  FileUtils.mkdir_p(File.join(reports_dir, folder))
end
FileUtils.mkdir_p(File.join(home, "handoffs"))

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
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; margin: 0; color: #171717; background: #fafafa; }
          main { max-width: 880px; margin: 0 auto; padding: 48px 24px 72px; background: #fff; min-height: 100vh; }
          h1, h2, h3 { line-height: 1.2; }
          h1 { margin-bottom: 4px; }
          .meta { color: #666; margin: 0 0 32px; }
          a { color: #075985; }
          table { border-collapse: collapse; width: 100%; }
          th, td { border: 1px solid #ddd; padding: 8px; vertical-align: top; }
          th { background: #f4f4f5; text-align: left; }
          code { background: #f4f4f5; padding: 0.1rem 0.25rem; border-radius: 4px; }
        </style>
      </head>
      <body>
        <main>
          <p><a href="../../index.html">Day Zero CTO index</a></p>
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

def report_links(home, kind)
  pattern = File.join(home, "reports", kind, "*.html")
  Dir.glob(pattern).sort.reverse
end

index_sections = REPORT_FOLDERS.map do |folder, label|
  links = report_links(home, folder)
  items =
    if links.empty?
      "<li>No reports yet.</li>"
    else
      links.map do |path|
        relative = Pathname.new(path).relative_path_from(Pathname.new(home)).to_s
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
  if File.exist?(path)
    "<li><a href=\"core/#{escape(doc)}\">#{escape(doc)}</a></li>"
  else
    "<li>#{escape(doc)} <span class=\"missing\">not created yet</span></li>"
  end
end.join("\n")

index_html = <<~HTML
  <!doctype html>
  <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Day Zero CTO</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; margin: 0; color: #171717; background: #fafafa; }
        main { max-width: 960px; margin: 0 auto; padding: 48px 24px 72px; background: #fff; min-height: 100vh; }
        h1, h2 { line-height: 1.2; }
        section { margin-top: 32px; }
        a { color: #075985; }
        .missing { color: #777; }
      </style>
    </head>
    <body>
      <main>
        <h1>Day Zero CTO</h1>
        <p>Bookmark this page to reach the startup's CTO context, reports, reviews, decisions, and handoffs.</p>

        <section>
          <h2>Core Context</h2>
          <ul>
            #{core_links}
          </ul>
        </section>

        #{index_sections}
      </main>
    </body>
  </html>
HTML

File.write(File.join(home, "index.html"), index_html)

puts written_report || File.join(home, "index.html")

#!/usr/bin/env ruby
# frozen_string_literal: true

require "date"
require "fileutils"
require "json"
require "optparse"
require "rbconfig"
require "set"

TARGET_NEW_RATE = 0.35
RECENT_WINDOW = 12
REVIEW_PRESSURE_LIMIT = 3
STALE_REVIEW_DAYS = 3
INTERVALS = [1, 3, 7, 14, 30, 60].freeze

RATINGS = {
  "needs_work" => {
    label: "Needs Work",
    aliases: ["needs work", "needs_work", "work", "not", "no", "missed", "lost", "rough", "0"]
  },
  "familiar" => {
    label: "Familiar",
    aliases: ["familiar", "neutral", "partial", "some", "fuzzy", "1"]
  },
  "confident" => {
    label: "Confident",
    aliases: ["confident", "know", "solid", "clear", "got it", "2"]
  }
}.freeze

options = {
  date: Date.today.iso8601,
  mode: :select
}

OptionParser.new do |parser|
  parser.banner = "Usage: dzcto-learning.rb --project PATH [--select | --add | --record RATING]"

  parser.on("--project PATH", "Project folder; uses PATH/knowledge/wiki/learning") { |value| options[:project] = value }
  parser.on("--date DATE", "Date, YYYY-MM-DD") { |value| options[:date] = value }
  parser.on("--select", "Select a learning item or recommend adding a new one") { options[:mode] = :select }
  parser.on("--add", "Add a new learning item and mark it current") { options[:mode] = :add }
  parser.on("--record RATING", "Record rating: Needs Work, Familiar, or Confident") do |value|
    options[:mode] = :record
    options[:rating] = value
  end
  parser.on("--stats", "Print learning stats") { options[:mode] = :stats }
  parser.on("--id ID", "Learning item id") { |value| options[:id] = value }
  parser.on("--title TITLE", "Learning item title") { |value| options[:title] = value }
  parser.on("--summary SUMMARY", "One-sentence learning item summary") { |value| options[:summary] = value }
  parser.on("--details DETAILS", "Learning item explanation") { |value| options[:details] = value }
  parser.on("--details-file PATH", "File containing learning item explanation") { |value| options[:details_file] = value }
  parser.on("--source SOURCE", "Source file or artifact") { |value| options[:source] = value }
  parser.on("--tags TAGS", "Comma-separated tags") { |value| options[:tags] = value }
  parser.on("--note NOTE", "Optional review note") { |value| options[:note] = value }
end.parse!

abort "--project is required" unless options[:project]

def slugify(value)
  value.to_s.downcase.gsub(/[^a-z0-9]+/, "-").gsub(/^-|-$/, "")
end

def date_value(value)
  Date.iso8601(value.to_s)
rescue Date::Error
  nil
end

def wiki_root(project)
  File.join(File.expand_path(project), "knowledge", "wiki")
end

def learning_dir(project)
  File.join(wiki_root(project), "learning")
end

def items_path(project)
  File.join(learning_dir(project), "items.json")
end

def reviews_path(project)
  File.join(learning_dir(project), "reviews.jsonl")
end

def current_path(project)
  File.join(learning_dir(project), "current.json")
end

def ensure_learning_dir(project)
  FileUtils.mkdir_p(learning_dir(project))
end

def load_items(project)
  ensure_learning_dir(project)
  return [] unless File.exist?(items_path(project))

  items = JSON.parse(File.read(items_path(project)))
  items.is_a?(Array) ? items : []
rescue JSON::ParserError
  []
end

def save_items(project, items)
  ensure_learning_dir(project)
  File.write(items_path(project), "#{JSON.pretty_generate(items)}\n")
end

def load_reviews(project)
  ensure_learning_dir(project)
  return [] unless File.exist?(reviews_path(project))

  File.readlines(reviews_path(project), chomp: true).map do |line|
    JSON.parse(line)
  rescue JSON::ParserError
    nil
  end.compact
end

def append_review(project, review)
  ensure_learning_dir(project)
  File.open(reviews_path(project), "a") { |file| file.puts(JSON.generate(review)) }
end

def load_current(project)
  return nil unless File.exist?(current_path(project))

  JSON.parse(File.read(current_path(project)))
rescue JSON::ParserError
  nil
end

def save_current(project, item, kind, today)
  File.write(
    current_path(project),
    "#{JSON.pretty_generate({ id: item["id"], kind: kind, selected_on: today.iso8601 })}\n"
  )
end

def clear_current(project)
  FileUtils.rm_f(current_path(project))
end

def refresh_index(project)
  script = File.join(__dir__, "dzcto-artifact.rb")
  ok = system(RbConfig.ruby, script, "--project", File.expand_path(project), "--init", out: File::NULL)
  warn "Warning: failed to refresh wiki index" unless ok
end

def output(payload)
  puts JSON.pretty_generate(payload)
end

def rating_options
  RATINGS.map do |key, config|
    {
      rating: key,
      label: config[:label]
    }
  end
end

def normalize_rating(value)
  normalized = value.to_s.strip.downcase
  RATINGS.each do |key, config|
    return key if config[:aliases].include?(normalized)
  end

  nil
end

def active_items(items)
  items.select { |item| item.fetch("status", "active") == "active" }
end

def sort_new_items(items)
  items.sort_by { |item| [item["created_on"].to_s, item["title"].to_s.downcase] }
end

def sort_due_items(items, today)
  items.sort_by do |item|
    due_on = date_value(item["due_on"]) || today
    [due_on, item.fetch("box", 0).to_i, item["last_seen_on"].to_s, item["title"].to_s.downcase]
  end
end

def choose_learning_item(items, reviews, today)
  active = active_items(items)
  new_items = active.select { |item| item.fetch("seen_count", 0).to_i.zero? }
  due_items = active.select do |item|
    due_on = date_value(item["due_on"])
    item.fetch("seen_count", 0).to_i.positive? && due_on && due_on <= today
  end

  if due_items.empty? && new_items.empty?
    return {
      kind: "new_needed",
      reason: "No due review items or unseen learning items exist. Create one new system concept from current project context."
    }
  end

  review_pressure = due_items.length >= REVIEW_PRESSURE_LIMIT ||
                    due_items.any? { |item| (date_value(item["due_on"]) || today) <= today - STALE_REVIEW_DAYS }

  kind =
    if due_items.any? && review_pressure
      "review"
    elsif due_items.any? && new_items.any?
      recent = reviews.last(RECENT_WINDOW)
      recent_new_rate =
        if recent.empty?
          0.0
        else
          recent.count { |review| review["kind"] == "new" }.fdiv(recent.length)
        end

      recent_new_rate < TARGET_NEW_RATE ? "new" : "review"
    elsif due_items.any?
      "review"
    else
      "new"
    end

  item =
    if kind == "review"
      sort_due_items(due_items, today).first
    else
      sort_new_items(new_items).first
    end

  {
    kind: kind,
    item: item,
    reason: kind == "review" ? "Selected from due review items." : "Selected from unseen learning items."
  }
end

def unique_id(base, items)
  candidate = slugify(base)
  candidate = "learning-item" if candidate.empty?
  taken = items.map { |item| item["id"] }.to_set
  return candidate unless taken.include?(candidate)

  counter = 2
  loop do
    next_candidate = "#{candidate}-#{counter}"
    return next_candidate unless taken.include?(next_candidate)

    counter += 1
  end
end

def item_payload(item)
  {
    id: item["id"],
    title: item["title"],
    summary: item["summary"],
    details: item["details"],
    source: item["source"],
    tags: item["tags"] || [],
    box: item.fetch("box", 0),
    seen_count: item.fetch("seen_count", 0),
    due_on: item["due_on"],
    last_rating: item["last_rating"]
  }
end

def learning_stats(items, today)
  active = active_items(items)
  due = active.count do |item|
    due_on = date_value(item["due_on"])
    item.fetch("seen_count", 0).to_i.positive? && due_on && due_on <= today
  end
  unseen = active.count { |item| item.fetch("seen_count", 0).to_i.zero? }

  {
    active: active.length,
    due: due,
    new: unseen
  }
end

project = File.expand_path(options[:project])
today = Date.iso8601(options[:date])
ensure_learning_dir(project)

case options[:mode]
when :select
  items = load_items(project)
  reviews = load_reviews(project)
  selection = choose_learning_item(items, reviews, today)

  if selection[:item]
    save_current(project, selection[:item], selection[:kind], today)
    output(
      status: "selected",
      kind: selection[:kind],
      reason: selection[:reason],
      item: item_payload(selection[:item]),
      rating_options: rating_options,
      algorithm: "Review debt first; otherwise target #{((1 - TARGET_NEW_RATE) * 100).round}% review and #{(TARGET_NEW_RATE * 100).round}% new over the last #{RECENT_WINDOW} logged sessions."
    )
  else
    output(
      status: "new_needed",
      kind: "new",
      reason: selection[:reason],
      rating_options: rating_options,
      algorithm: "Review debt first; otherwise target #{((1 - TARGET_NEW_RATE) * 100).round}% review and #{(TARGET_NEW_RATE * 100).round}% new over the last #{RECENT_WINDOW} logged sessions."
    )
  end
when :add
  abort "--title is required with --add" unless options[:title]
  abort "--summary is required with --add" unless options[:summary]

  items = load_items(project)
  details =
    if options[:details_file]
      File.read(File.expand_path(options[:details_file]))
    else
      options[:details].to_s
    end
  id = options[:id] || unique_id(options[:title], items)
  tags = options[:tags].to_s.split(",").map(&:strip).reject(&:empty?)
  existing = items.find { |item| item["id"] == id }

  item = existing || {
    "id" => id,
    "created_on" => today.iso8601,
    "seen_count" => 0,
    "box" => 0,
    "status" => "active"
  }

  item.merge!(
    "title" => options[:title],
    "summary" => options[:summary],
    "details" => details,
    "source" => options[:source] || "Unknown",
    "tags" => tags,
    "due_on" => item["due_on"] || today.iso8601
  )

  items << item unless existing
  save_items(project, items)
  save_current(project, item, "new", today)
  refresh_index(project)

  output(
    status: existing ? "updated" : "added",
    kind: "new",
    item: item_payload(item),
    rating_options: rating_options
  )
when :record
  rating = normalize_rating(options[:rating])
  abort "Unknown rating '#{options[:rating]}'. Use Needs Work, Familiar, or Confident." unless rating

  items = load_items(project)
  current = load_current(project)
  id = options[:id] || current&.fetch("id", nil)
  abort "No current learning item. Run --select or pass --id." unless id

  item = items.find { |candidate| candidate["id"] == id }
  abort "Unknown learning item id '#{id}'" unless item

  previous_box = item.fetch("box", 0).to_i
  previous_seen_count = item.fetch("seen_count", 0).to_i
  kind = current&.fetch("kind", nil) || (previous_seen_count.zero? ? "new" : "review")

  next_box =
    case rating
    when "needs_work"
      [previous_box - 1, 0].max
    when "familiar"
      [previous_box + 1, INTERVALS.length - 1].min
    when "confident"
      [previous_box + 2, INTERVALS.length - 1].min
    end

  interval = rating == "needs_work" ? 1 : INTERVALS.fetch(next_box)
  due_on = today + interval
  item["box"] = next_box
  item["seen_count"] = previous_seen_count + 1
  item["last_seen_on"] = today.iso8601
  item["last_rating"] = RATINGS.fetch(rating)[:label]
  item["due_on"] = due_on.iso8601

  review = {
    reviewed_on: today.iso8601,
    id: item["id"],
    title: item["title"],
    kind: kind,
    rating: rating,
    rating_label: RATINGS.fetch(rating)[:label],
    previous_box: previous_box,
    next_box: next_box,
    previous_seen_count: previous_seen_count,
    next_seen_count: item["seen_count"],
    due_on: due_on.iso8601,
    note: options[:note]
  }.compact

  save_items(project, items)
  append_review(project, review)
  clear_current(project)
  refresh_index(project)

  output(
    status: "recorded",
    review: review,
    item: item_payload(item),
    stats: learning_stats(items, today)
  )
when :stats
  items = load_items(project)
  output(status: "stats", stats: learning_stats(items, today), rating_options: rating_options)
end

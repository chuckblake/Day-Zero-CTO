#!/usr/bin/env ruby
# frozen_string_literal: true

require "json"
require "fileutils"

REPO_ROOT = File.expand_path("..", __dir__)
PLUGIN_NAME = "day-zero-cto"
PLUGIN_LINK = File.expand_path("~/plugins/#{PLUGIN_NAME}")
MARKETPLACE_PATH = File.expand_path("~/.agents/plugins/marketplace.json")

def write_marketplace_entry
  FileUtils.mkdir_p(File.dirname(MARKETPLACE_PATH))

  payload =
    if File.exist?(MARKETPLACE_PATH)
      JSON.parse(File.read(MARKETPLACE_PATH))
    else
      {
        "name" => "personal",
        "interface" => {
          "displayName" => "Personal"
        },
        "plugins" => []
      }
    end

  payload["plugins"] ||= []

  entry = {
    "name" => PLUGIN_NAME,
    "source" => {
      "source" => "local",
      "path" => "./plugins/#{PLUGIN_NAME}"
    },
    "policy" => {
      "installation" => "AVAILABLE",
      "authentication" => "ON_INSTALL"
    },
    "category" => "Productivity"
  }

  index = payload["plugins"].find_index { |plugin| plugin.is_a?(Hash) && plugin["name"] == PLUGIN_NAME }

  if index
    payload["plugins"][index] = entry
  else
    payload["plugins"] << entry
  end

  File.write(MARKETPLACE_PATH, JSON.pretty_generate(payload) + "\n")
end

FileUtils.mkdir_p(File.dirname(PLUGIN_LINK))

if File.symlink?(PLUGIN_LINK)
  current_target = File.expand_path(File.readlink(PLUGIN_LINK), File.dirname(PLUGIN_LINK))
  if current_target != REPO_ROOT
    FileUtils.rm_f(PLUGIN_LINK)
    FileUtils.ln_s(REPO_ROOT, PLUGIN_LINK)
  end
elsif File.exist?(PLUGIN_LINK)
  abort "#{PLUGIN_LINK} already exists and is not a symlink. Move it aside, then rerun this script."
else
  FileUtils.ln_s(REPO_ROOT, PLUGIN_LINK)
end

write_marketplace_entry

puts "Installed #{PLUGIN_NAME} for Codex Desktop."
puts "Plugin link: #{PLUGIN_LINK} -> #{REPO_ROOT}"
puts "Marketplace: #{MARKETPLACE_PATH}"
puts "Restart Codex Desktop to pick it up."

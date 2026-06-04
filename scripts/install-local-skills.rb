#!/usr/bin/env ruby
# frozen_string_literal: true

require "fileutils"

REPO_ROOT = File.expand_path("..", __dir__)
SKILLS_DIR = File.join(REPO_ROOT, "skills")
DEST_DIR = File.expand_path("~/.codex/skills")

abort "Missing skills directory: #{SKILLS_DIR}" unless File.directory?(SKILLS_DIR)

FileUtils.mkdir_p(DEST_DIR)

Dir.glob(File.join(SKILLS_DIR, "*")).sort.each do |source|
  next unless File.directory?(source)

  name = File.basename(source)
  destination = File.join(DEST_DIR, name)

  if File.symlink?(destination)
    current_target = File.expand_path(File.readlink(destination), File.dirname(destination))
    if current_target == source
      puts "Already linked #{name}"
      next
    end

    FileUtils.rm_f(destination)
  elsif File.exist?(destination)
    abort "#{destination} already exists and is not a symlink. Move it aside, then rerun this script."
  end

  FileUtils.ln_s(source, destination)
  puts "Linked #{name}"
end

puts "Installed editable Day Zero CTO skills into #{DEST_DIR}."
puts "Restart Codex Desktop or start a fresh session to reload skill metadata."

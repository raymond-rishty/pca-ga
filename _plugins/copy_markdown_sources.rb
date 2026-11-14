# Preserve Markdown source beside each Jekyll-rendered HTML page.
require "fileutils"

Jekyll::Hooks.register :site, :post_write do |site|
  site.pages.each do |page|
    relative_path = page.path.to_s.tr("\\", "/")
    next unless relative_path.downcase.end_with?(".md")

    source_path = File.expand_path(relative_path, site.source)
    destination_path = File.expand_path(relative_path, site.dest)
    source_root = File.expand_path(site.source) + File::SEPARATOR
    destination_root = File.expand_path(site.dest) + File::SEPARATOR
    next unless source_path.start_with?(source_root)
    next unless destination_path.start_with?(destination_root)
    next unless File.file?(source_path)

    FileUtils.mkdir_p(File.dirname(destination_path))
    FileUtils.cp(source_path, destination_path)
  end
end

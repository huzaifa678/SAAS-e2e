package main

import rego.v1

test_deny_latest_base if {
	count(deny) > 0 with input as [{"Cmd": "from", "Value": ["python:latest"]}]
}

test_deny_untagged_base if {
	count(deny) > 0 with input as [{"Cmd": "from", "Value": ["python"]}]
}

# Mirrors this repo's Dockerfile: pinned slim base + numeric non-root UID.
test_allow_pinned_numeric_nonroot if {
	count(deny) == 0 with input as [
		{"Cmd": "from", "Value": ["python:3.11-slim", "AS", "runtime"]},
		{"Cmd": "user", "Value": ["10001"]},
	]
}

test_deny_user_root if {
	count(deny) > 0 with input as [
		{"Cmd": "from", "Value": ["python:3.11-slim"]},
		{"Cmd": "user", "Value": ["root"]},
	]
}

test_deny_user_uid_zero if {
	count(deny) > 0 with input as [
		{"Cmd": "from", "Value": ["python:3.11-slim"]},
		{"Cmd": "user", "Value": ["0"]},
	]
}

# root in a build stage, dropped to non-root in the final stage → allowed
test_allow_root_then_nonroot if {
	count(deny) == 0 with input as [
		{"Cmd": "from", "Value": ["python:3.11-slim", "AS", "builder"]},
		{"Cmd": "user", "Value": ["root"]},
		{"Cmd": "user", "Value": ["10001"]},
	]
}

test_deny_add_remote_url if {
	count(deny) > 0 with input as [
		{"Cmd": "from", "Value": ["python:3.11-slim"]},
		{"Cmd": "add", "Value": ["https://example.com/x.tar", "/x"]},
	]
}

# No USER at all still warns (advisory, non-blocking).
test_warn_no_user if {
	count(deny) == 0 with input as [{"Cmd": "from", "Value": ["python:3.11-slim"]}]
	count(warn) > 0 with input as [{"Cmd": "from", "Value": ["python:3.11-slim"]}]
}

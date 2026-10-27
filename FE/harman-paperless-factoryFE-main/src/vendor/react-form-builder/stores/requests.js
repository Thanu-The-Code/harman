// the browser's own fetch (isomorphic-fetch was only needed for server rendering)

const headers = {
  Accept: 'application/json',
  'Content-Type': 'application/json; charset=utf-8',
  OPTIONS: '',
};

export function post(url, data) {
  return fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  }).then(response => response);
}

export function get(url) {
  return fetch(url, {
    method: 'GET',
    headers,
  }).then(response => response.json());
}

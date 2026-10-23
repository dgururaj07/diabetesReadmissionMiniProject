async function getpublicapi(){
    const baseUrl = "http://127.0.0.1:8000";
    const response = await fetch(`${baseUrl}/encounters`);
    console.log(await response.ok)
    console.log(await response.json())
    console.log(await response.status)
}


getpublicapi()
from fastapi import APIRouter


router = APIRouter(
    prefix="/chats",
    tags=["chats"],
)


@router.get("")
async def get_chats():
    return [
        {
            "id": 1,
            "username": "Marco",
            "last_message": "Привет! Как дела?",
        },
        {
            "id": 2,
            "username": "Emma",
            "last_message": "Увидимся завтра",
        },
    ]